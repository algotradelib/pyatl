"""`Replay` and `backtest()`: a Python strategy over bar data, replayed by algotradelib in C++."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

import numpy as np

from . import _core


@dataclass(frozen=True)
class BacktestResult:
    """What one replay produced.

    `fills`, `equity`, `rejected` and `refused` are dicts of columns (`pandas.DataFrame(result.fills)` makes
    a table). Times are ns since the epoch (UTC). `halted` says why the replay stopped early, if it did; the
    figures then cover only what ran. Figures are NaN where the library has none.

    Attributes
    ----------
    bars : int
        Bars replayed.
    fills : dict of str to array
        One row per fill: `time`, `symbol`, `side` ("buy" or "sell"), `quantity`, `price` (slippage
        included), `commission`, `tax` (sale tax, KRW) and `slippage` (the price per share given up to
        slippage, already in `price`).
    equity : dict of str to array
        The equity curve: `time` and `equity`, one point per period end.
    opening_equity, closing_equity : str
        Equity at the first and last point, as exact decimal text.
    halted : str or None
        Why the replay stopped early, or None.
    total_return, sharpe, annualized_sharpe, max_drawdown, sortino : float
        The library's summary of the equity curve.
    turnover : float
        One-way turnover over the run: the fraction of equity traded.
    commission_paid, tax_paid, slippage_paid : float
        Costs over the run, KRW; NaN where the library cannot state a total.
    rejected : dict of str to list
        Targets the runner could not turn into an order: `symbol` and `reason` (the library's name).
    refused : dict of str to array
        Orders the risk guard refused: `symbol`, `reason` (the library's name), and the `limit` exceeded and
        the value `attempted`, NaN where the reason has none.
    unfilled : int
        Orders still waiting when the replay ended.
    gaps : int
        Bars that did not follow the bar before them; nothing is interpolated across a gap.
    unvalued_bars : int
        Bars at which the equity could not be valued exactly (a total too large for an exact decimal); such
        a bar has no point in `equity`. The library's own figures leave the next period's return out; a
        return computed between two exported points would span the missing bar. Check it is 0 before
        computing measures from `equity` per period.
    lowest_cash : float
        The lowest cash an execution left, if cash went below zero; NaN otherwise.
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
    sortino: float
    turnover: float
    commission_paid: float
    tax_paid: float
    slippage_paid: float
    rejected: dict[str, Any]
    refused: dict[str, Any]
    unfilled: int
    gaps: int
    unvalued_bars: int
    lowest_cash: float


class Replay:
    """One backtest that you feed yourself, in as many steps as you like, then finish once.

    `backtest()` is a `Replay` fed once. Use a `Replay` when the sequence of bars is yours to define: a
    resampled path, a rolling window, bars generated as the run goes. The bars still run through the C++
    engine one at a time, so feeding in blocks costs no more than one `backtest()` call.

    Parameters
    ----------
    strategy : object
        An object with `on_bar(ctx, bar)` or `on_bars(ctx, bars)` (not both), and optionally `on_stop(ctx)`.
        A target set at a bar's close fills at the next bar's open. `on_start` is refused: the library's
        replay never calls it, so set up in `__init__`.
    symbols : sequence of str
        Every symbol the replay may receive. Their order breaks ties between bars of the same period.
    interval : str
        The bars' interval, as the library names it ("1m", "5m", "15m", "30m", "1h", "1d", "1w", "1mo",
        "1y").
    stamp : str
        "open" if a bar's time is its period's start, "close" if its end.
    cash : int, str or Decimal
        Starting cash, KRW.
    commission : float, str or Decimal
        Commission rate on every fill (0.00015 is 0.015 %).
    min_commission : int, str or Decimal
        Minimum commission per fill, KRW.
    sell_tax : float, str or Decimal
        Securities transaction tax rate on sales.
    slippage_ticks : int
        Price ticks against the order on each fill.
    scale : int
        Decimal places kept when prices and volumes are converted to exact decimals.

    Notes
    -----
    Every feed is checked whole before its first bar reaches the engine: each symbol's bars must come later
    than its previous one, and no bar may end before the bar fed before it. A refused feed raises
    `ValueError` and changes nothing. An exception raised by the strategy ends the replay: later calls raise
    `RuntimeError`. A strategy handler may not feed or finish its own replay.
    """

    def __init__(
        self,
        strategy: Any,
        symbols: Sequence[str],
        *,
        interval: str = "1d",
        stamp: str = "open",
        cash: int | str | Decimal = 100_000_000,
        commission: float | str | Decimal = 0,
        min_commission: int | str | Decimal = 0,
        sell_tax: float | str | Decimal = 0,
        slippage_ticks: int = 0,
        scale: int = 4,
    ) -> None:
        symbols = list(symbols)
        for symbol in symbols:
            if not isinstance(symbol, str):
                raise TypeError(f"a symbol is a str (keeping leading zeros, '005930'), not {type(symbol).__name__}")
        settings = _core.Settings()
        settings.cash = _decimal(cash)
        settings.commission = _decimal(commission)
        settings.min_commission = _decimal(min_commission)
        settings.sell_tax = _decimal(sell_tax)
        settings.slippage_ticks = slippage_ticks
        self._interval, self._stamp, self._scale = interval, stamp, scale
        self._core = _core.Replay(strategy, symbols, settings, interval, stamp)
        self._index = {symbol: i for i, symbol in enumerate(symbols)}

    @property
    def symbols(self) -> tuple[str, ...]:
        """The symbols the replay may receive, in the order that breaks ties."""
        return tuple(self._core.symbols)

    def feed(self, data: Mapping[str, Any]) -> None:
        """Feeds whole series, one per symbol, merged by time.

        Parameters
        ----------
        data : mapping of str to frame
            Symbol to bars, as `backtest()` takes them: a pandas or polars DataFrame, or a mapping of arrays,
            with `open` (optional), `high`, `low`, `close`, `volume`, and the time as a `time` column or a
            pandas DatetimeIndex. A symbol's rows may come in any order; two rows for the same period are
            refused.
        """
        series = [_series(symbol, frame, self._interval, self._stamp, self._scale) for symbol, frame in data.items()]
        self._core.feed_series(series)

    def feed_bars(
        self,
        symbol: Any,
        time: Any,
        *,
        high: Any,
        low: Any,
        close: Any,
        volume: Any,
        open: Any = None,
    ) -> None:
        """Feeds bars in the order given: the sequence you define.

        Parameters
        ----------
        symbol : array of int or str
            Each bar's symbol: an index into `symbols`, or the symbol itself.
        time : array of datetime64
            Each bar's time; naive is read as UTC, integers are refused.
        high, low, close, volume : array of float
            Each bar's prices and volume.
        open : array of float, optional
            Each bar's open; omitted or NaN where the source has none.
        """
        time_ns = _time_ns(time)
        n = len(time_ns)
        open_ = np.full(n, np.nan) if open is None else _array(open)
        self._core.feed_bars(
            self._codes(symbol, n), time_ns, open_, _array(high), _array(low), _array(close), _array(volume),
            self._scale,
        )

    def finish(self) -> BacktestResult:
        """Ends the replay: calls `on_stop`, fills nothing further, and returns the result."""
        return BacktestResult(**self._core.finish())

    def _codes(self, symbol: Any, n: int) -> np.ndarray:
        array = np.asarray(symbol)
        if array.ndim != 1 or len(array) != n:
            raise ValueError("symbol must be a one-dimensional array with as many rows as time")
        if array.dtype.kind in "iu":
            return np.ascontiguousarray(array, dtype=np.int64)
        if array.dtype.kind in "UOT":  # T: NumPy 2's StringDType
            labels, inverse = np.unique(array, return_inverse=True)
            try:
                codes = np.array([self._index[label] for label in labels.tolist()], dtype=np.int64)
            except KeyError as error:
                raise ValueError(f"unknown symbol: {error.args[0]!r}") from None
            except TypeError:
                raise TypeError("symbol labels must be str") from None
            return np.ascontiguousarray(codes[inverse.reshape(-1)])
        raise TypeError(f"symbol is an array of int (indices into symbols) or of str, not {array.dtype}")


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

    Parameters
    ----------
    strategy : object
        An object with `on_bar(ctx, bar)` or `on_bars(ctx, bars)` (not both), and optionally `on_stop(ctx)`.
        A target set at a bar's close fills at the next bar's open. `on_start` is refused: the library's
        replay never calls it, so set up in `__init__`.
    data : mapping of str to frame
        Symbol to bars. Each value is a pandas or polars DataFrame, or a mapping of arrays, with `open`
        (optional), `high`, `low`, `close`, `volume`, and the time as a `time` column or a pandas
        DatetimeIndex. The time must be datetime64 (naive is read as UTC); integers are refused rather than
        guessed (`pd.to_datetime(df.ts, unit="s")`).
    interval, stamp, cash, commission, min_commission, sell_tax, slippage_ticks, scale
        As for `Replay`.

    Returns
    -------
    BacktestResult
        The fills, the equity curve and the summary figures.
    """
    if not data:
        raise ValueError("no series given")
    replay = Replay(
        strategy, list(data), interval=interval, stamp=stamp, cash=cash, commission=commission,
        min_commission=min_commission, sell_tax=sell_tax, slippage_ticks=slippage_ticks, scale=scale,
    )
    replay.feed(data)
    return replay.finish()


def _decimal(value: Any) -> str:
    """Exact decimal text; a float goes through its shortest repr (0.00015, not 0.000149999...)."""
    if isinstance(value, float):
        value = Decimal(repr(value))
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _array(values: Any) -> np.ndarray:
    return np.ascontiguousarray(np.asarray(values, dtype=np.float64))


def _column(frame: Any, name: str) -> np.ndarray:
    return _array(frame[name])


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
