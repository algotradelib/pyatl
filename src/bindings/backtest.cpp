// run_backtest: picks the adapter for the Python strategy, replays, and returns the result as a dict.
// The only binding file that compiles the engine.
#include "bindings.hpp"

#include <pyatl/backtest.hpp>

#include <nanobind/ndarray.h>
#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>
#include <nanobind/stl/vector.h>

namespace nb = nanobind;
using namespace nb::literals;

namespace pyatl {
namespace {

nb::dict to_dict(Result r) {
  auto array = [](auto values) {
    using T = typename decltype(values)::value_type;
    auto* owned = new std::vector<T>(std::move(values));
    nb::capsule owner(owned, [](void* p) noexcept { delete static_cast<std::vector<T>*>(p); });
    return nb::ndarray<nb::numpy, T, nb::ndim<1>>(owned->data(), {owned->size()}, owner);
  };
  nb::dict fills;
  fills["time"] = array(std::move(r.fill_time));
  fills["symbol"] = nb::cast(r.fill_symbol);
  fills["side"] = nb::cast(r.fill_side);
  fills["quantity"] = array(std::move(r.fill_quantity));
  fills["price"] = array(std::move(r.fill_price));
  fills["commission"] = array(std::move(r.fill_commission));
  nb::dict equity;
  equity["time"] = array(std::move(r.equity_time));
  equity["equity"] = array(std::move(r.equity));
  nb::dict d;
  d["bars"] = r.bars;
  d["fills"] = fills;
  d["equity"] = equity;
  d["opening_equity"] = r.opening_equity;
  d["closing_equity"] = r.closing_equity;
  d["halted"] = r.halted;
  d["total_return"] = r.total_return;
  d["sharpe"] = r.sharpe;
  d["annualized_sharpe"] = r.annualized_sharpe;
  d["max_drawdown"] = r.max_drawdown;
  return d;
}

nb::dict run_backtest(nb::object strategy, const std::vector<Series>& series, const Settings& settings) {
  std::unordered_map<std::string, atl::InstrumentId> ids;
  for (const auto& s : series) {
    if (!ids.emplace(s.symbol, instrument_of(s.symbol)).second) throw std::invalid_argument("symbol given twice: " + s.symbol);
    if (s.interval != series.front().interval) throw std::invalid_argument("every series must have the same interval");
  }
  if (nb::hasattr(strategy, "on_start")) {
    // The library's replay never calls on_start; a setup step that silently never runs is worse than none.
    throw nb::type_error("on_start is not called by algotradelib's replay; do the setup in __init__");
  }
  Handlers handlers(strategy, ids, atl::Currency{"KRW"});
  const bool bar = !handlers.on_bar.is_none(), bars = !handlers.on_bars.is_none();
  if (bar == bars) {
    throw nb::type_error(bar ? "a strategy defines on_bar or on_bars, not both: on_bar receives each bar, "
                               "on_bars every instrument's bar for a period at once"
                             : "a strategy must define on_bar(ctx, bar) or on_bars(ctx, bars)");
  }
  Result result = bar ? replay(PyOnBar{{&handlers}}, series, settings) : replay(PyOnBars{{&handlers}}, series, settings);
  return to_dict(std::move(result));
}

} // namespace
} // namespace pyatl

void pyatl::bind_backtest(nb::module_& m) {
  m.def("run_backtest", &run_backtest, "strategy"_a, "series"_a, "settings"_a);
}
