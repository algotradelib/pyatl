"""Python strategies on algotradelib's C++ replay.

A strategy is any object with `on_bar(ctx, bar)` or `on_bars(ctx, bars)`; it needs no base class:

    class Hold:
        def on_bar(self, ctx, bar):
            ctx.target(bar.symbol, 10)

    result = pyatl.backtest(Hold(), {"005930": frame})
"""
import sys as _sys
from importlib.metadata import version as _version

from . import _backtest
from ._backtest import BacktestResult, Replay, backtest
from ._core import ALGOTRADELIB_VERSION as algotradelib_version
from ._core import Bar, Context

# The module was named pyatl.backtest before; keep `from pyatl.backtest import ...` and the module path named in pickles
# made then resolving, while the package's `backtest` attribute stays the function. A result pickled before a field
# was added loads without that field.
_sys.modules[__name__ + ".backtest"] = _backtest

__version__ = _version("pyatl")
__all__ = ["Bar", "Context", "BacktestResult", "Replay", "backtest", "algotradelib_version", "__version__"]
