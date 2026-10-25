// Bar and Context, as a strategy handler receives them.
#include "bindings.hpp"

#include <pyatl/views.hpp>

#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>

namespace nb = nanobind;
using namespace nb::literals;

void pyatl::bind_types(nb::module_& m) {
  nb::class_<Bar>(m, "Bar", "One bar. Valid as a value only during the handler call that received it.")
    .def_ro("symbol", &Bar::symbol)
    .def_ro("time", &Bar::time, "The period end, ns since the epoch (UTC).")
    .def_ro("open", &Bar::open, "NaN when the source has no open.")
    .def_ro("high", &Bar::high)
    .def_ro("low", &Bar::low)
    .def_ro("close", &Bar::close)
    .def_ro("volume", &Bar::volume)
    .def("__repr__", [](const Bar& b) {
      return "Bar(" + b.symbol + ", time=" + std::to_string(b.time) + ", close=" + std::to_string(b.close) + ")";
    });

  nb::class_<Context>(m, "Context", "The running replay. Valid only inside a handler call.")
    .def_prop_ro("now", &Context::now, "The replay's clock, ns since the epoch (UTC).")
    .def("target", &Context::target, "symbol"_a, "quantity"_a,
         "Hold `quantity` of `symbol`; the runner sends the orders the difference needs, filled at the next bar's open.")
    .def("position", &Context::position, "symbol"_a, "The net quantity held.")
    .def("cash", &Context::cash, "Cash in the replay's currency, or None if none is recorded.");
}
