import inspect
import re
import shutil
import subprocess
import sys

import pytest

import pyatl
from pyatl import _core


def test_the_library_version_is_reported():
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.\d+)?", pyatl.algotradelib_version)


def test_backtest_is_the_function_not_a_module():
    assert callable(pyatl.backtest)
    assert inspect.isfunction(pyatl.backtest)
    assert pyatl._backtest.backtest is pyatl.backtest


@pytest.mark.parametrize("name", [n for n in pyatl.__all__ if n not in ("algotradelib_version", "__version__")])
def test_every_public_name_is_documented(name):
    doc = inspect.getdoc(getattr(pyatl, name)) or ""
    assert doc.strip(), name
    if name in ("backtest", "Replay"):
        assert "Parameters\n----------" in doc, name
    if name in ("BacktestResult", "Replay", "Bar", "Context"):
        # A class with attributes documents them in its own section; quartodoc otherwise links a summary table
        # to attribute sections it does not render.
        assert "Attributes\n----------" in doc, name


@pytest.mark.parametrize("cls, members", [
    (pyatl.Bar, ["symbol", "time", "open", "high", "low", "close", "volume"]),
    (pyatl.Context, ["now", "target", "position", "cash"]),
])
def test_every_binding_member_is_documented(cls, members):
    for member in members:
        assert (inspect.getdoc(getattr(cls, member)) or "").strip(), f"{cls.__name__}.{member}"


@pytest.mark.skipif(sys.platform != "darwin" or shutil.which("otool") is None, reason="macOS's otool")
def test_the_extension_links_only_system_libraries_on_macos():
    listing = subprocess.run(["otool", "-L", _core.__file__], capture_output=True, text=True, check=True).stdout
    libraries = [line.split()[0] for line in listing.splitlines()[1:] if line.strip()]
    assert libraries and all(lib.startswith("/usr/lib/") or lib.startswith("/System/") for lib in libraries), libraries


def test_the_old_module_path_still_imports_and_unpickles():
    import importlib
    import pickle

    import numpy as np
    import pandas as pd

    from pyatl.backtest import BacktestResult, backtest  # noqa: F401

    assert importlib.import_module("pyatl.backtest") is pyatl._backtest
    assert callable(pyatl.backtest)

    class Hold:
        def on_bar(self, ctx, bar):
            ctx.target(bar.symbol, 1)

    frame = pd.DataFrame({"open": [1.0, 2.0], "high": [1.0, 2.0], "low": [1.0, 2.0], "close": [1.0, 2.0],
                          "volume": [1.0, 1.0]}, index=pd.date_range("2024-01-01", periods=2))
    result = pyatl.backtest(Hold(), {"005930": frame})
    # A pickle names the class's module; one made when the class lived in pyatl.backtest names that path.
    old = pickle.dumps(result, protocol=0).replace(b"pyatl._backtest", b"pyatl.backtest")
    assert b"pyatl.backtest\n" in old
    loaded = pickle.loads(old)
    assert loaded.closing_equity == result.closing_equity
    assert np.array_equal(loaded.equity["equity"], result.equity["equity"])
