# pyatl

Python strategies on [algotradelib](https://github.com/algotradelib/algotradelib)'s C++ backtest.
You write the strategy in Python; the replay, the fills and the costs run in C++.

```python
import pandas as pd
import pyatl

class Hold:
    def on_bar(self, ctx, bar):
        ctx.target(bar.symbol, 10)  # hold 10 shares, bought at the next bar's open

frame = pd.read_csv("bars.csv", parse_dates=["time"])
result = pyatl.backtest(Hold(), {"005930": frame}, commission=0.00015, sell_tax=0.002)
print(result.closing_equity, result.total_return)
```

## Install

pyatl needs an installed algotradelib; see [its install guide](https://github.com/algotradelib/algotradelib#install).
Then:

```sh
pip install .
```

If algotradelib is installed under a prefix CMake does not search, set `CMAKE_PREFIX_PATH` to that prefix.

## Writing a strategy

A strategy is any object with these methods; it needs no base class.

| Method | Called |
| --- | --- |
| `on_bar(ctx, bar)` | for each bar, in time order |
| `on_bars(ctx, bars)` | once per period, with every symbol's bar for it (instead of `on_bar`) |
| `on_stop(ctx)` | after the last bar (optional) |

Set the strategy up in `__init__`: `on_start` is not supported.

- `bar`: `symbol`, `time` (the period end, ns since the epoch, UTC), `open`, `high`, `low`, `close`, `volume`.
- `ctx`: `now`, `target(symbol, quantity)`, `position(symbol)`, `cash()`.

Both are valid only during the call; keep the numbers, not the objects.

`backtest()` takes a dict of symbol to bars: a pandas or polars DataFrame, or a dict of arrays.
The time is a `time` column or a pandas `DatetimeIndex`, as datetime64; integer times are refused.
[`examples/sma_crossover.py`](examples/sma_crossover.py) is a complete strategy.

## Status

Early.
It backtests Korean (KRX) stocks with target positions in whole shares.
Other markets, limit orders and live trading are not supported yet.

## License

MIT
