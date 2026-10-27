// Series from NumPy columns, and the replay settings.
#include "bindings.hpp"

#include <pyatl/series.hpp>

#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>

namespace nb = nanobind;
using namespace nb::literals;

namespace pyatl {
namespace {

using Times = nb::ndarray<const std::int64_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using Values = nb::ndarray<const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;

Series make_series(const std::string& symbol, Times time, Values open, Values high, Values low, Values close,
                   Values volume, const std::string& interval, const std::string& stamp, int scale) {
  const auto n = time.shape(0);
  for (const auto* column : {&open, &high, &low, &close, &volume}) {
    if (column->shape(0) != n) throw std::invalid_argument("every column must have as many rows as time");
  }
  const auto s = checked_scale(scale);
  Series series;
  series.symbol = symbol;
  series.interval = parse_interval(interval);
  series.stamp = parse_stamp(stamp);
  series.bars.reserve(n);
  for (std::size_t i = 0; i < n; ++i) {
    series.bars.push_back(bar_of(time(i), open(i), high(i), low(i), close(i), volume(i), s, i));
  }
  order_series(series);
  return series;
}

} // namespace
} // namespace pyatl

void pyatl::bind_series(nb::module_& m) {
  nb::class_<Series>(m, "Series")
    .def_ro("symbol", &Series::symbol)
    .def_prop_ro("size", [](const Series& s) { return s.bars.size(); });

  m.def("make_series", &make_series, "symbol"_a, "time"_a, "open"_a, "high"_a, "low"_a, "close"_a, "volume"_a,
        "interval"_a, "stamp"_a, "scale"_a);

  nb::class_<Settings>(m, "Settings")
    .def(nb::init<>())
    .def_rw("cash", &Settings::cash)
    .def_rw("commission", &Settings::commission)
    .def_rw("min_commission", &Settings::min_commission)
    .def_rw("sell_tax", &Settings::sell_tax)
    .def_rw("slippage_ticks", &Settings::slippage_ticks);
}
