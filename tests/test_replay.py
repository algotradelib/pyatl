import gc
import weakref

import numpy as np
import pandas as pd
import pytest

import pyatl


def frame(closes, start="2024-01-01", freq="D"):
    """Bars whose open, high, low and close are all `closes`."""
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": np.full(len(closes), 1000.0)},
        index=pd.date_range(start, periods=len(closes), freq=freq),
    )


def long_table(data):
    """The same bars as one table in feed order: by time, then by the order of `data`."""
    rows = []
    for position, (symbol, f) in enumerate(data.items()):
        for time, row in f.iterrows():
            rows.append((time, position, symbol, row["open"], row["high"], row["low"], row["close"], row["volume"]))
    rows.sort(key=lambda r: (r[0], r[1]))
    table = pd.DataFrame(rows, columns=["time", "position", "symbol", "open", "high", "low", "close", "volume"])
    return table.drop(columns="position")


class Rebalance:
    """on_bar: buys 10 of a symbol on its 2nd bar and sells on its 4th; records what it saw."""

    def __init__(self):
        self.count, self.seen = {}, []

    def on_bar(self, ctx, bar):
        self.seen.append((bar.symbol, bar.time))
        n = self.count.get(bar.symbol, 0)
        if n == 1:
            ctx.target(bar.symbol, 10)
        elif n == 3:
            ctx.target(bar.symbol, 0)
        self.count[bar.symbol] = n + 1


class RebalanceBars:
    """on_bars: holds 5 of every symbol on odd periods and none on even ones; records each period."""

    def __init__(self):
        self.period, self.seen = 0, []

    def on_bars(self, ctx, bars):
        self.seen.append([(b.symbol, b.time) for b in bars])
        for b in bars:
            ctx.target(b.symbol, 5 if self.period % 2 else 0)
        self.period += 1


def same(a, b):
    assert a.bars == b.bars
    for key in ("time", "symbol", "side", "quantity", "price"):
        assert list(a.fills[key]) == list(b.fills[key]), key
    assert list(a.equity["equity"]) == list(b.equity["equity"])
    assert a.closing_equity == b.closing_equity


DATA = {
    "005930": frame([100, 101, 103, 102, 105, 107, 106, 108]),
    "000660": frame([50, 52, 51, 53, 55, 54, 56, 57], start="2024-01-03"),
    "035720": frame([30, 31, 29, 28, 30, 33], start="2024-01-02"),
}


@pytest.mark.parametrize("make", [Rebalance, RebalanceBars])
def test_feeding_in_chunks_or_blocks_equals_backtest(make):
    whole = pyatl.backtest(make(), DATA)

    chunked = pyatl.Replay(make(), list(DATA))
    for lo, hi in (("2024-01-01", "2024-01-03"), ("2024-01-04", "2024-01-04"), ("2024-01-05", "2024-12-31")):
        chunked.feed({s: f.loc[lo:hi] for s, f in DATA.items()})
    same(whole, chunked.finish())

    table = long_table(DATA)
    blocks = pyatl.Replay(make(), list(DATA))
    # Uneven blocks; the cut at row 4 splits 2024-01-03's bars across two calls.
    for lo, hi in ((0, 4), (4, 9), (9, len(table))):
        part = table.iloc[lo:hi]
        blocks.feed_bars(part["symbol"].to_numpy(), part["time"].to_numpy(), open=part["open"], high=part["high"],
                         low=part["low"], close=part["close"], volume=part["volume"])
    same(whole, blocks.finish())


def test_string_and_integer_symbols_are_the_same_and_map_through_the_registry():
    data = {"B": frame([1, 2, 3, 4]), "A": frame([5, 6, 7, 8])}
    table = long_table(data)
    by_name = pyatl.Replay(Rebalance(), ["B", "A"])
    by_name.feed_bars(table["symbol"].to_numpy(), table["time"].to_numpy(), high=table["high"], low=table["low"],
                      close=table["close"], volume=table["volume"])
    by_index = pyatl.Replay(Rebalance(), ["B", "A"])
    codes = np.array([{"B": 0, "A": 1}[s] for s in table["symbol"]])
    by_index.feed_bars(codes, table["time"].to_numpy(), high=table["high"], low=table["low"], close=table["close"],
                       volume=table["volume"])
    same(by_name.finish(), by_index.finish())

    only_a = pyatl.Replay(Rebalance(), ["B", "A"])
    a = data["A"]
    only_a.feed_bars(np.array(["A"] * len(a)), a.index.to_numpy(), high=a["high"], low=a["low"], close=a["close"],
                     volume=a["volume"])
    result = only_a.finish()
    assert set(result.fills["symbol"]) == {"A"}


def test_ties_follow_the_symbols_order_not_the_mapping_order():
    strategy = Rebalance()
    replay = pyatl.Replay(strategy, ["A", "B"])
    replay.feed({"B": frame([1, 2]), "A": frame([3, 4])})
    replay.finish()
    assert [s for s, _ in strategy.seen] == ["A", "B", "A", "B"]


def test_backtest_keeps_the_data_order_for_ties():
    strategy = Rebalance()
    pyatl.backtest(strategy, {"B": frame([1, 2]), "A": frame([3, 4])})
    assert [s for s, _ in strategy.seen] == ["B", "A", "B", "A"]


@pytest.mark.parametrize("make", [Rebalance, RebalanceBars])
def test_rows_out_of_order_are_sorted_by_backtest_and_feed(make):
    f = frame([100, 101, 102, 103])
    shuffled = f.iloc[[2, 0, 3, 1]]
    same(pyatl.backtest(make(), {"005930": f}), pyatl.backtest(make(), {"005930": shuffled}))
    replay = pyatl.Replay(make(), ["005930"])
    replay.feed({"005930": shuffled})
    same(pyatl.backtest(make(), {"005930": f}), replay.finish())


def test_feed_bars_takes_rows_as_given_and_refuses_them_out_of_order():
    f = frame([100, 101, 102]).iloc[[1, 0, 2]]
    replay = pyatl.Replay(Rebalance(), ["005930"])
    with pytest.raises(ValueError, match="not later than its previous bar"):
        replay.feed_bars(["005930"] * 3, f.index.to_numpy(), high=f["high"], low=f["low"], close=f["close"],
                         volume=f["volume"])


def test_two_rows_for_the_same_period_are_refused_naming_both():
    f = frame([100, 101, 102])
    doubled = pd.concat([f, f.iloc[[1]]])
    with pytest.raises(ValueError, match="rows 1 and 3 are bars for the same period"):
        pyatl.backtest(Rebalance(), {"005930": doubled})


def test_misaligned_symbols_merge_in_time_then_symbol_order():
    # Every symbol on its own minutes: each step feeds one bar of many heads, so the merge falls back to its heap.
    symbols = [f"{i:06d}" for i in range(120)]
    data = {s: frame(np.arange(1, 61), start=pd.Timestamp("2024-01-02 09:00") + pd.Timedelta(seconds=i), freq="min")
            for i, s in enumerate(symbols)}
    strategy = Rebalance()
    pyatl.backtest(strategy, data, interval="1m")
    expected = sorted(((t, symbols.index(s)) for s in symbols for t in data[s].index))
    assert [(pd.Timestamp(t, unit="ns"), symbols.index(s)) for s, t in strategy.seen] == \
        [(t + pd.Timedelta(minutes=1), i) for t, i in expected]


def refused_but_usable(replay, call, match):
    with pytest.raises(ValueError, match=match):
        call()
    replay.feed({"005930": frame([100, 101])})  # still usable
    return replay.finish()


def test_refusals_leave_the_replay_usable():
    f = frame([100, 101, 102], start="2023-06-01")
    later = frame([100, 101, 102], start="2025-01-01")

    def block(r, f, symbols=None):
        symbols = ["005930"] * len(f) if symbols is None else symbols
        return lambda: r.feed_bars(symbols, f.index.to_numpy(), high=f["high"], low=f["low"], close=f["close"],
                                   volume=f["volume"])

    r = pyatl.Replay(Rebalance(), ["005930"])
    refused_but_usable(r, block(r, f, ["XXXXXX"] * 3), "unknown symbol")
    r = pyatl.Replay(Rebalance(), ["005930"])
    refused_but_usable(r, lambda: r.feed({"XXXXXX": f}), "unknown symbol")
    r = pyatl.Replay(Rebalance(), ["005930"])
    refused_but_usable(r, lambda: r.feed_bars(np.array([0, 1, 0]), f.index.to_numpy(), high=f["high"], low=f["low"],
                                               close=f["close"], volume=f["volume"]), "symbol index 1")
    r = pyatl.Replay(Rebalance(), ["005930"])
    refused_but_usable(r, lambda: r.feed_bars(["005930"] * 2, f.index.to_numpy(), high=f["high"], low=f["low"],
                                               close=f["close"], volume=f["volume"]), "as many rows")
    nan_close = f.assign(close=[100.0, np.nan, 102.0])
    r = pyatl.Replay(Rebalance(), ["005930"])
    refused_but_usable(r, block(r, nan_close), "close at row 1")

    # After a later block, an earlier one is refused, and the replay goes on.
    r = pyatl.Replay(Rebalance(), ["005930", "000660"])
    block(r, later)()
    with pytest.raises(ValueError, match="ends before the bar fed before it"):
        block(r, f, ["000660"] * 3)()
    with pytest.raises(ValueError, match="earliest bar given ends before"):
        r.feed({"000660": f})
    with pytest.raises(ValueError, match="not later than the last bar fed"):
        r.feed({"005930": later})
    block(r, frame([103], start="2025-01-04"))()
    assert r.finish().bars == 4


def test_a_float_index_array_is_refused_not_cast():
    f = frame([100, 101])
    r = pyatl.Replay(Rebalance(), ["005930"])
    with pytest.raises(TypeError, match="array of int"):
        r.feed_bars(np.array([0.0, 0.0]), f.index.to_numpy(), high=f["high"], low=f["low"], close=f["close"],
                    volume=f["volume"])


def test_integer_times_and_non_str_symbols_are_refused():
    with pytest.raises(TypeError, match="datetime64"):
        pyatl.Replay(Rebalance(), ["005930"]).feed_bars([0], np.array([1]), high=[1.0], low=[1.0], close=[1.0],
                                                        volume=[1.0])
    with pytest.raises(TypeError, match="a symbol is a str"):
        pyatl.Replay(Rebalance(), [5930])


def test_finish_once_and_no_feed_after_it():
    r = pyatl.Replay(Rebalance(), ["005930"])
    r.feed({"005930": frame([1, 2])})
    r.finish()
    with pytest.raises(RuntimeError, match="has finished"):
        r.finish()
    with pytest.raises(RuntimeError, match="has finished"):
        r.feed({"005930": frame([3], start="2024-02-01")})


def test_a_strategy_exception_ends_the_replay():
    class Broken:
        def on_bar(self, ctx, bar):
            raise ZeroDivisionError("from the strategy")

    r = pyatl.Replay(Broken(), ["005930"])
    with pytest.raises(ZeroDivisionError, match="from the strategy"):
        r.feed({"005930": frame([1, 2])})
    with pytest.raises(RuntimeError, match="failed: .*from the strategy"):
        r.feed({"005930": frame([3], start="2024-02-01")})
    with pytest.raises(RuntimeError, match="failed"):
        r.finish()


@pytest.mark.parametrize("where", ["on_bar", "on_bars", "on_stop"])
@pytest.mark.parametrize("caught", [True, False])
def test_a_handler_cannot_feed_or_finish_its_own_replay(where, caught):
    class Reenter:
        def __init__(self):
            self.replay, self.refused = None, 0

        def poke(self):
            try:
                self.replay.feed({"005930": frame([9], start="2030-01-01")})
            except RuntimeError as error:
                assert "inside its own strategy handler" in str(error)
                self.refused += 1
                if not caught:
                    raise

    if where == "on_bar":
        class S(Reenter):
            def on_bar(self, ctx, bar):
                self.poke()
    elif where == "on_bars":
        class S(Reenter):
            def on_bars(self, ctx, bars):
                self.poke()
    else:
        class S(Reenter):
            def on_bar(self, ctx, bar):
                pass

            def on_stop(self, ctx):
                self.poke()

    strategy = S()
    replay = pyatl.Replay(strategy, ["005930"])
    strategy.replay = replay
    if caught:
        replay.feed({"005930": frame([1, 2])})
        assert replay.finish().bars == 2
        assert strategy.refused >= 1
    else:
        with pytest.raises(RuntimeError, match="inside its own strategy handler"):
            replay.feed({"005930": frame([1, 2])})
            replay.finish()
        with pytest.raises(RuntimeError, match="failed"):
            replay.finish()


@pytest.mark.parametrize("state", ["unfinished", "finished", "failed"])
def test_a_strategy_that_keeps_its_replay_is_collected(state):
    class Keeper:
        def on_bar(self, ctx, bar):
            if bar.close > 50:
                raise ValueError("fail on purpose")

    strategy = Keeper()
    replay = pyatl.Replay(strategy, ["005930"])
    strategy.replay = replay
    if state == "finished":
        replay.feed({"005930": frame([1, 2])})
        replay.finish()
    elif state == "failed":
        with pytest.raises(ValueError):
            replay.feed({"005930": frame([1, 99])})
    else:
        replay.feed({"005930": frame([1, 2])})
    alive = weakref.ref(strategy)
    del strategy, replay
    gc.collect()
    assert alive() is None


def test_a_kept_ctx_raises_after_the_replay_is_gone_or_failed():
    class Keep:
        def on_bar(self, ctx, bar):
            self.ctx = ctx
            if bar.close > 50:
                raise ValueError("fail on purpose")

    strategy = Keep()
    replay = pyatl.Replay(strategy, ["005930"])
    with pytest.raises(ValueError):
        replay.feed({"005930": frame([1, 99])})
    with pytest.raises(RuntimeError, match="only inside a strategy handler"):
        strategy.ctx.target("005930", 1)
    del replay
    gc.collect()
    with pytest.raises(RuntimeError, match="only inside a strategy handler"):
        strategy.ctx.position("005930")


def test_a_failure_whose_message_cannot_be_formatted_still_ends_the_replay():
    class BadStr(Exception):
        def __str__(self):
            raise ValueError("stringification failed")

    class Broken:
        def on_bar(self, ctx, bar):
            raise BadStr("original exception")

    strategy = Broken()
    r = pyatl.Replay(strategy, ["A"])
    f = frame([1])
    with pytest.raises(BadStr):
        r.feed_bars([0], f.index.to_numpy(), high=f["high"], low=f["low"], close=f["close"], volume=f["volume"])
    with pytest.raises(RuntimeError, match="failed: .*BadStr"):
        r.finish()
    alive = weakref.ref(strategy)
    del strategy
    gc.collect()
    assert alive() is None  # the failed replay no longer holds the strategy's handlers


def test_backtest_without_series_is_refused():
    with pytest.raises(ValueError, match="no series given"):
        pyatl.backtest(Rebalance(), {})


def test_numpy_string_dtype_symbols_are_accepted():
    string_dtype = getattr(np.dtypes, "StringDType", None)
    if string_dtype is None:
        pytest.skip("NumPy without StringDType")
    f = frame([1, 2, 3, 4])
    by_string_dtype = pyatl.Replay(Rebalance(), ["005930"])
    by_string_dtype.feed_bars(np.array(["005930"] * 4, dtype=string_dtype()), f.index.to_numpy(), high=f["high"],
                              low=f["low"], close=f["close"], volume=f["volume"])
    same(pyatl.backtest(Rebalance(), {"005930": f}), by_string_dtype.finish())
