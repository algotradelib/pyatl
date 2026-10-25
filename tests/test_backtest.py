import math

import numpy as np
import pandas as pd
import pytest

import pyatl


def frame(closes, start="2024-01-01"):
    """Daily bars whose open, high, low and close are all `closes`."""
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": np.full(len(closes), 1000.0)},
        index=pd.date_range(start, periods=len(closes), freq="D"),
    )


class TargetAt:
    """Targets `quantity` on bar `on` and 0 on bar `off` (by count)."""

    def __init__(self, on, off, quantity=10):
        self.on, self.off, self.quantity, self.seen = on, off, quantity, 0

    def on_bar(self, ctx, bar):
        if self.seen == self.on:
            ctx.target(bar.symbol, self.quantity)
        elif self.seen == self.off:
            ctx.target(bar.symbol, 0)
        self.seen += 1


def test_a_target_fills_at_the_next_bar_open():
    data = {"005930": frame([100, 110, 120, 130, 140, 150, 160])}
    result = pyatl.backtest(TargetAt(on=0, off=3), data)
    assert result.bars == 7
    assert list(result.fills["side"]) == ["buy", "sell"]
    assert list(result.fills["quantity"]) == [10, 10]
    assert list(result.fills["price"]) == [110, 140]  # bar 1's and bar 4's open
    assert float(result.closing_equity) == 100_000_000 + 10 * (140 - 110)
    assert result.halted is None


def test_costs_are_charged():
    data = {"005930": frame([100, 100, 100, 100])}
    result = pyatl.backtest(TargetAt(on=0, off=1, quantity=1000), data, commission=0.001, sell_tax=0.002)
    # 0.1 % on each 100,000 fill, 0.2 % tax on the sale
    assert float(result.closing_equity) == pytest.approx(100_000_000 - 100 - 100 - 200)


def test_on_bars_receives_every_symbol_for_a_period():
    class Slices:
        def __init__(self):
            self.sizes = []

        def on_bars(self, ctx, bars):
            self.sizes.append(sorted(b.symbol for b in bars))

    strategy = Slices()
    pyatl.backtest(strategy, {"005930": frame([1, 2, 3]), "000660": frame([4, 5, 6])})
    assert strategy.sizes == [["000660", "005930"]] * 3


def test_position_and_cash_follow_the_fills():
    class Watch(TargetAt):
        def __init__(self):
            super().__init__(on=0, off=99)
            self.positions, self.cash = [], []

        def on_bar(self, ctx, bar):
            self.positions.append(ctx.position(bar.symbol))
            self.cash.append(ctx.cash())
            super().on_bar(ctx, bar)

    strategy = Watch()
    pyatl.backtest(strategy, {"005930": frame([100, 110, 120])})
    assert strategy.positions == [0, 10, 10]
    assert strategy.cash[0] == 100_000_000
    assert strategy.cash[1] == 100_000_000 - 10 * 110


def test_on_stop_is_called_after_the_last_bar():
    class Lifecycle:
        def __init__(self):
            self.calls = []

        def on_bar(self, ctx, bar):
            self.calls.append("bar")

        def on_stop(self, ctx):
            self.calls.append("stop")

    strategy = Lifecycle()
    pyatl.backtest(strategy, {"005930": frame([1, 2])})
    assert strategy.calls == ["bar", "bar", "stop"]


def test_on_start_is_refused_because_the_replay_never_calls_it():
    class Starts:
        def on_start(self, ctx): ...
        def on_bar(self, ctx, bar): ...

    with pytest.raises(TypeError, match="on_start is not called"):
        pyatl.backtest(Starts(), {"005930": frame([1])})


def test_an_exception_in_the_strategy_reaches_the_caller():
    class Broken:
        def on_bar(self, ctx, bar):
            raise ZeroDivisionError("from the strategy")

    with pytest.raises(ZeroDivisionError, match="from the strategy"):
        pyatl.backtest(Broken(), {"005930": frame([1, 2])})


def test_ctx_outside_a_handler_raises():
    class Keep:
        def on_bar(self, ctx, bar):
            self.ctx = ctx

    strategy = Keep()
    pyatl.backtest(strategy, {"005930": frame([1, 2])})
    with pytest.raises(RuntimeError, match="only inside a strategy handler"):
        strategy.ctx.target("005930", 1)


def test_both_or_neither_bar_handler_is_refused():
    class Both:
        def on_bar(self, ctx, bar): ...
        def on_bars(self, ctx, bars): ...

    with pytest.raises(TypeError, match="not both"):
        pyatl.backtest(Both(), {"005930": frame([1])})
    with pytest.raises(TypeError, match="must define"):
        pyatl.backtest(object(), {"005930": frame([1])})


def test_integer_times_are_refused():
    data = {"time": np.arange(3), "high": [1.0] * 3, "low": [1.0] * 3, "close": [1.0] * 3, "volume": [1.0] * 3}
    with pytest.raises(TypeError, match="datetime64"):
        pyatl.backtest(TargetAt(0, 1), {"005930": data})


def test_a_dict_of_arrays_with_a_time_column_works():
    data = {
        "time": np.array(["2024-01-01", "2024-01-02", "2024-01-03"], dtype="datetime64[D]"),
        "high": [1.0, 2.0, 3.0], "low": [1.0, 2.0, 3.0], "close": [1.0, 2.0, 3.0], "volume": [1.0] * 3,
    }
    result = pyatl.backtest(TargetAt(0, 99, quantity=1), {"005930": data})
    assert result.bars == 3
    assert math.isnan(result.fills["price"][0]) is False


def test_unknown_interval_lists_the_known_ones():
    with pytest.raises(ValueError, match="1m, 1d"):
        pyatl.backtest(TargetAt(0, 1), {"005930": frame([1])}, interval="2d")
