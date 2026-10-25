"""An SMA crossover written in Python, replayed by algotradelib.

    python examples/sma_crossover.py BARS.csv SYMBOL [--interval 1d]

BARS.csv has open, high, low, close, volume, and the time as `time` (any format pandas reads) or `ts`
(epoch seconds).
"""
import argparse
from collections import deque

import pandas as pd

import pyatl


class SmaCross:
    """Holds `quantity` while the fast mean of the closes is above the slow one, nothing otherwise.

    Rolling sums, not a recomputed window each bar: per-bar pandas or NumPy over a window costs more than
    the rest of the replay.
    """

    def __init__(self, fast=20, slow=60, quantity=100):
        self.fast, self.slow, self.quantity = fast, slow, quantity
        self.closes = deque(maxlen=slow)
        self.sum_fast = self.sum_slow = 0.0

    def on_bar(self, ctx, bar):
        closes = self.closes
        if len(closes) == self.slow:
            self.sum_slow -= closes[0]
        if len(closes) >= self.fast:
            self.sum_fast -= closes[-self.fast]
        closes.append(bar.close)
        self.sum_slow += bar.close
        self.sum_fast += bar.close
        if len(closes) < self.slow:
            return
        above = self.sum_slow / self.slow < self.sum_fast / self.fast
        ctx.target(bar.symbol, self.quantity if above else 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("symbol")
    parser.add_argument("--interval", default="1d")
    args = parser.parse_args()

    frame = pd.read_csv(args.csv)
    frame["time"] = pd.to_datetime(frame["ts"], unit="s") if "ts" in frame else pd.to_datetime(frame["time"])
    result = pyatl.backtest(
        SmaCross(), {args.symbol: frame}, interval=args.interval,
        commission=0.00015, sell_tax=0.002,  # a Korean online brokerage's order of magnitude
    )
    print(f"bars {result.bars}, fills {len(result.fills['side'])}")
    print(f"equity {result.opening_equity} -> {result.closing_equity}")
    print(f"total return {result.total_return:.2%}, max drawdown {result.max_drawdown:.2%}")
    if result.halted:
        print(f"halted: {result.halted}")


if __name__ == "__main__":
    main()
