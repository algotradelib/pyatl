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


def bars(opens, closes=None, start="2024-01-01"):
    closes = opens if closes is None else closes
    opens, closes = np.asarray(opens, dtype=float), np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": opens, "high": np.maximum(opens, closes), "low": np.minimum(opens, closes), "close": closes,
         "volume": np.full(len(opens), 1000.0)},
        index=pd.date_range(start, periods=len(opens), freq="D"),
    )


def test_sale_tax_is_reported_per_fill_and_in_total():
    result = pyatl.backtest(TargetAt(on=0, off=1, quantity=100), {"005930": bars([12000] * 4)}, sell_tax=0.002)
    assert list(result.fills["side"]) == ["buy", "sell"]
    assert list(result.fills["tax"]) == [0, pytest.approx(0.002 * 100 * 12000)]
    assert result.tax_paid == pytest.approx(0.002 * 100 * 12000)


def test_slippage_is_per_share_one_tick_and_already_in_the_price():
    # 12,000 KRW sits inside KRX's 10 KRW tick band (5,000 to 20,000), away from a band edge.
    result = pyatl.backtest(TargetAt(on=0, off=1, quantity=100), {"005930": bars([12000] * 4)}, slippage_ticks=1)
    assert list(result.fills["price"]) == [12010, 11990]
    assert list(result.fills["slippage"]) == [10, 10]
    assert result.slippage_paid == pytest.approx(10 * 100 * 2)


def test_commission_paid_is_the_sum_of_the_fills():
    result = pyatl.backtest(TargetAt(on=0, off=2, quantity=100), {"005930": bars([12000, 12100, 12200, 12300])},
                            commission=0.00015)
    assert result.commission_paid == pytest.approx(float(np.sum(result.fills["commission"])))


def test_a_sale_of_shares_not_held_is_refused_with_the_library_reason():
    class Short:
        def __init__(self):
            self.n = 0

        def on_bar(self, ctx, bar):
            if self.n == 0:
                ctx.target(bar.symbol, -5)
            self.n += 1

    result = pyatl.backtest(Short(), {"005930": bars([100] * 3)})
    assert result.refused["symbol"] == ["005930"]
    assert result.refused["reason"] == ["quantity_not_sellable"]
    assert math.isnan(result.refused["limit"][0]) and math.isnan(result.refused["attempted"][0])
    assert result.rejected == {"symbol": [], "reason": []}
    assert len(result.fills["time"]) == 0


def test_a_target_on_the_last_bar_is_left_unfilled():
    result = pyatl.backtest(TargetAt(on=2, off=99, quantity=1), {"005930": bars([100] * 3)})
    assert result.unfilled == 1
    assert len(result.fills["time"]) == 0


def test_cash_below_zero_is_reported():
    result = pyatl.backtest(TargetAt(on=0, off=99, quantity=1000), {"005930": bars([100] * 3)}, cash=1000)
    assert result.lowest_cash == pytest.approx(1000 - 1000 * 100)


def test_an_unvalued_bar_is_counted_and_has_no_equity_point():
    # Cash near the exact decimal's maximum: two shares marked at 1,000,000 make a total that does not fit.
    data = {"005930": bars([70000] * 4, [70000, 70000, 70000, 1_000_000])}
    result = pyatl.backtest(TargetAt(on=0, off=99, quantity=2), data, cash="9223372036854000000", scale=0)
    assert result.halted is None
    assert result.bars == 4
    assert result.unvalued_bars == 1
    assert len(result.equity["equity"]) == 3


def test_sortino_and_turnover_come_from_the_library():
    closes = [12000, 12500, 11800, 12300, 11900, 12600]
    result = pyatl.backtest(TargetAt(on=0, off=4, quantity=100), {"005930": bars(closes)})
    assert math.isfinite(result.sortino)
    assert result.turnover > 0
    assert result.gaps == 0 and result.unvalued_bars == 0 and math.isnan(result.lowest_cash)


def test_costs_are_reported_even_with_no_equity_point():
    # One bar each; the order fills on 000660's bar of the same period, whose equity does not fit an exact decimal.
    def one_bar(close):
        return dict(time=np.array(["2024-01-01"], dtype="datetime64[D]"), open=[70000], high=[max(70000, close)],
                    low=[min(70000, close)], close=[close], volume=[1000])

    class Cross:
        def on_bar(self, ctx, bar):
            if bar.symbol == "005930":
                ctx.target("000660", 2)

    result = pyatl.backtest(Cross(), {"005930": one_bar(70000), "000660": one_bar(1_000_000)},
                            cash="9223372036854000000", scale=0, commission="0.001", slippage_ticks=1)
    assert len(result.equity["equity"]) == 0 and result.unvalued_bars == 1
    assert len(result.fills["time"]) == 1
    assert result.commission_paid == pytest.approx(float(result.fills["commission"][0]))
    assert result.tax_paid == 0
    assert result.slippage_paid == pytest.approx(float(result.fills["slippage"][0]) * 2)


def test_a_target_the_runner_cannot_plan_is_rejected_with_the_library_reason():
    # Holding 1, a target of -2**63 makes a difference no exact decimal holds.
    class Overflow:
        def __init__(self):
            self.n = 0

        def on_bar(self, ctx, bar):
            ctx.target(bar.symbol, 1 if self.n == 0 else -(2**63))
            self.n += 1

    result = pyatl.backtest(Overflow(), {"005930": bars([1] * 3)}, scale=0)
    # One rejection for each callback after the first (the 2nd and 3rd bars).
    assert result.rejected == {"symbol": ["005930", "005930"], "reason": ["not_representable", "not_representable"]}
    assert result.halted is None
