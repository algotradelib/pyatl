"""`backtest()`: a Python strategy over bar data, replayed by algotradelib in C++."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

import numpy as np

from . import _core


@dataclass(frozen=True)
class BacktestResult:
    """What one replay produced.

    `fills` and `equity` are dicts of NumPy columns (`pandas.DataFrame(result.fills)` makes a table).
    Times are ns since the epoch (UTC). `halted` says why the replay stopped early, if it did; the figures
    then cover only what ran. Summary figures are NaN where they do not exist.
    """

    bars: int
    fills: dict[str, Any]
    equity: dict[str, Any]
    opening_equity: str
    closing_equity: str
    halted: str | None
    total_return: float
    sharpe: float
    annualized_sharpe: float
    max_drawdown: float


def backtest(
    strategy: Any,
    data: Mapping[str, Any],
    *,
    interval: str = "1d",
    stamp: str = "open",
    cash: int | str | Decimal = 100_000_000,
    commission: float | str | Decimal = 0,
    min_commission: int | str | Decimal = 0,
    sell_tax: float | str | Decimal = 0,
    slippage_ticks: int = 0,
    scale: int = 4,
) -> BacktestResult:
    """Replays `data` through `strategy` and returns the result.

    Args:
        strategy: An object with `on_bar(ctx, bar)` or `on_bars(ctx, bars)` (not both), and optionally
            `on_stop(ctx)`. A target set at a bar's close fills at the next bar's open. `on_start` is
            refused: the library's replay never calls it, so set up in `__init__`.
        data: Symbol to bars. Each value is a pandas or polars DataFrame, or a mapping of arrays, with
            `open` (optional), `high`, `low`, `close`, `volume`, and the time as a `time` column or a
            pandas DatetimeIndex. The time must be datetime64 (naive is read as UTC); integers are refused
            rather than guessed (`pd.to_datetime(df.ts, unit="s")`).
        interval: The bars' interval, as the library names it ("1m", "5m", "15m", "30m", "1h", "1d",
            "1w", "1mo", "1y").
        stamp: "open" if a bar's time is its period's start, "close" if its end.
        cash: Starting cash, KRW.
        commission: Commission rate on every fill (0.00015 is 0.015 %).
        min_commission: Minimum commission per fill, KRW.
        sell_tax: Securities transaction tax rate on sales.
        slippage_ticks: Price ticks against the order on each fill.
        scale: Decimal places kept when prices and volumes are converted to exact decimals.
    """
    series = [_series(symbol, frame, interval, stamp, scale) for symbol, frame in data.items()]
    settings = _core.Settings()
    settings.cash = _decimal(cash)
    settings.commission = _decimal(commission)
    settings.min_commission = _decimal(min_commission)
    settings.sell_tax = _decimal(sell_tax)
    settings.slippage_ticks = slippage_ticks
    return BacktestResult(**_core.run_backtest(strategy, series, settings))


def _decimal(value: Any) -> str:
    """Exact decimal text; a float goes through its shortest repr (0.00015, not 0.000149999...)."""
    if isinstance(value, float):
        value = Decimal(repr(value))
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _column(frame: Any, name: str) -> np.ndarray:
    return np.ascontiguousarray(np.asarray(frame[name], dtype=np.float64))


def _has(frame: Any, name: str) -> bool:
    try:
        return name in frame
    except TypeError:
        return False


def _time_ns(values: Any) -> np.ndarray:
    tz = getattr(getattr(values, "dtype", None), "tz", None)
    if tz is not None:  # pandas, timezone-aware: to UTC, then naive
        if hasattr(values, "tz_convert"):
            values = values.tz_convert("UTC").tz_localize(None)
        else:
            values = values.dt.tz_convert("UTC").dt.tz_localize(None)
    array = np.asarray(values)
    if array.dtype.kind != "M":
        raise TypeError(
            f"the time must be datetime64, not {array.dtype}; convert it first, e.g. pd.to_datetime(df.ts, unit='s')"
        )
    return np.ascontiguousarray(array.astype("datetime64[ns]").view(np.int64))


def _series(symbol: str, frame: Any, interval: str, stamp: str, scale: int) -> _core.Series:
    time = frame["time"] if _has(frame, "time") else getattr(frame, "index", None)
    if time is None:
        raise ValueError(f"{symbol}: no 'time' column and no DatetimeIndex")
    time_ns = _time_ns(time)
    open_ = _column(frame, "open") if _has(frame, "open") else np.full(len(time_ns), np.nan)
    return _core.make_series(
        symbol, time_ns, open_, _column(frame, "high"), _column(frame, "low"), _column(frame, "close"),
        _column(frame, "volume"), interval, stamp, scale,
    )
