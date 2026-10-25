"""Python strategies on algotradelib's C++ replay.

A strategy is any object with `on_bar(ctx, bar)` or `on_bars(ctx, bars)`; it needs no base class:

    class Hold:
        def on_bar(self, ctx, bar):
            ctx.target(bar.symbol, 10)

    result = pyatl.backtest(Hold(), {"005930": frame})
"""
from importlib.metadata import version as _version

from ._core import Bar, Context
from .backtest import BacktestResult, backtest

__version__ = _version("pyatl")
__all__ = ["Bar", "Context", "BacktestResult", "backtest", "__version__"]
