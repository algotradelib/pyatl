// Replay: one run, fed from Python, finished into a dict. The only binding file that compiles the engine.
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

using Indices = nb::ndarray<const std::int64_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using Times = nb::ndarray<const std::int64_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using Values = nb::ndarray<const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;

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

void feed_bars(Replay& replay, Indices symbol, Times time, Values open, Values high, Values low, Values close,
               Values volume, int scale) {
  const auto n = time.shape(0);
  if (symbol.shape(0) != n) throw std::invalid_argument("symbol must have as many rows as time");
  for (const auto* column : {&open, &high, &low, &close, &volume}) {
    if (column->shape(0) != n) throw std::invalid_argument("every column must have as many rows as time");
  }
  const auto s = checked_scale(scale);
  const auto count = static_cast<std::int64_t>(replay.symbol_count());
  Block block;
  block.symbol.reserve(n);
  block.bars.reserve(n);
  block.ends.reserve(n);
  for (std::size_t i = 0; i < n; ++i) {
    if (symbol(i) < 0 || symbol(i) >= count) {
      throw std::invalid_argument("symbol index " + std::to_string(symbol(i)) + " at row " + std::to_string(i) +
                                  " is not one of the replay's " + std::to_string(count) + " symbols");
    }
    block.symbol.push_back(static_cast<std::size_t>(symbol(i)));
    block.bars.push_back(bar_of(time(i), open(i), high(i), low(i), close(i), volume(i), s, i));
    block.ends.push_back(atl::strategy::bar_period_end(block.bars.back(), replay.interval(), replay.stamp()));
  }
  replay.feed_block(block);
}

// The garbage collector's view of a replay: the Python objects its handlers keep (the strategy's bound methods),
// so a cycle through a strategy that keeps its replay can be collected (nanobind's reference-leak guide).
int replay_traverse(PyObject* self, visitproc visit, void* arg) {
  Py_VISIT(Py_TYPE(self));
  if (!nb::inst_ready(self)) return 0;
  return nb::inst_ptr<Replay>(self)->traverse([&](PyObject* object) {
    Py_VISIT(object);
    return 0;
  });
}

int replay_clear(PyObject* self) {
  if (nb::inst_ready(self)) nb::inst_ptr<Replay>(self)->clear();
  return 0;
}

PyType_Slot replay_slots[] = {
  {Py_tp_traverse, reinterpret_cast<void*>(replay_traverse)},
  {Py_tp_clear, reinterpret_cast<void*>(replay_clear)},
  {0, nullptr},
};

} // namespace
} // namespace pyatl

void pyatl::bind_backtest(nb::module_& m) {
  nb::class_<Replay>(m, "Replay", nb::type_slots(replay_slots))
    .def(nb::init<nb::handle, const std::vector<std::string>&, const Settings&, const std::string&, const std::string&>(),
         "strategy"_a, "symbols"_a, "settings"_a, "interval"_a, "stamp"_a)
    .def_prop_ro("symbols", &Replay::symbols)
    .def("feed_series", &Replay::feed_series, "series"_a)
    .def("feed_bars", &feed_bars, "symbol"_a, "time"_a, "open"_a, "high"_a, "low"_a, "close"_a, "volume"_a, "scale"_a)
    .def("finish", [](Replay& replay) { return to_dict(replay.finish()); });
}
