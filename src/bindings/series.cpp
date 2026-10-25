// Series from NumPy columns, and the replay settings.
#include "bindings.hpp"

#include <pyatl/series.hpp>
#include <pyatl/views.hpp>

#include <nanobind/ndarray.h>
#include <nanobind/stl/string.h>

#include <cmath>

namespace nb = nanobind;
using namespace nb::literals;

namespace pyatl {
namespace {

using Times = nb::ndarray<const std::int64_t, nb::ndim<1>, nb::c_contig, nb::device::cpu>;
using Values = nb::ndarray<const double, nb::ndim<1>, nb::c_contig, nb::device::cpu>;

atl::Decimal64 exact(double value, std::uint8_t scale, const char* field, std::size_t row) {
  const auto decimal = atl::analytics::to_decimal(value, scale);
  if (!decimal) {
    throw std::invalid_argument(std::string(field) + " at row " + std::to_string(row) + " is not a representable decimal");
  }
  return *decimal;
}

Series make_series(const std::string& symbol, Times time, Values open, Values high, Values low, Values close,
                   Values volume, const std::string& interval, const std::string& stamp, int scale) {
  const auto n = time.shape(0);
  for (const auto* column : {&open, &high, &low, &close, &volume}) {
    if (column->shape(0) != n) throw std::invalid_argument("every column must have as many rows as time");
  }
  if (scale < 0 || scale > 18) throw std::invalid_argument("scale is 0 to 18");
  const auto s = static_cast<std::uint8_t>(scale);
  Series series;
  series.symbol = symbol;
  series.interval = parse_interval(interval);
  series.stamp = parse_stamp(stamp);
  series.bars.reserve(n);
  for (std::size_t i = 0; i < n; ++i) {
    atl::Bar bar;
    bar.timestamp_ = from_ns(time(i));
    if (!std::isnan(open(i))) bar.open_ = exact(open(i), s, "open", i);
    bar.high_ = exact(high(i), s, "high", i);
    bar.low_ = exact(low(i), s, "low", i);
    bar.close_ = exact(close(i), s, "close", i);
    bar.volume_ = exact(volume(i), s, "volume", i);
    series.bars.push_back(std::move(bar));
  }
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
