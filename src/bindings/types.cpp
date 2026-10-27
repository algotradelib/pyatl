// Bar and Context, as a strategy handler receives them.
#include "bindings.hpp"

#include <pyatl/views.hpp>

#include <nanobind/stl/optional.h>
#include <nanobind/stl/string.h>

namespace nb = nanobind;
using namespace nb::literals;

void pyatl::bind_types(nb::module_& m) {
  nb::class_<Bar>(m, "Bar",
                  "One bar, as a strategy handler receives it.\n\n"
                  "The replay reuses bar objects from call to call: keep the numbers, not the object.\n")
    .def_ro("symbol", &Bar::symbol, "The symbol the bar is for.")
    .def_ro("time", &Bar::time, "The period end, ns since the epoch (UTC).")
    .def_ro("open", &Bar::open, "The open price; NaN when the source has no open.")
    .def_ro("high", &Bar::high, "The high price.")
    .def_ro("low", &Bar::low, "The low price.")
    .def_ro("close", &Bar::close, "The close price.")
    .def_ro("volume", &Bar::volume, "The volume traded.")
    .def("__repr__", [](const Bar& b) {
      return "Bar(" + b.symbol + ", time=" + std::to_string(b.time) + ", close=" + std::to_string(b.close) + ")";
    });

  nb::class_<Context>(m, "Context",
                      "The running replay, as a strategy handler sees it.\n\n"
                      "Valid only inside the handler call that received it; afterwards every method raises\n"
                      "RuntimeError.\n")
    .def_prop_ro("now", &Context::now, "The replay's clock: the end of the period being handled, ns since the epoch (UTC).")
    .def("target", &Context::target, "symbol"_a, "quantity"_a,
         "Hold a number of shares of a symbol.\n\n"
         "The runner sends the orders the difference from the current position and working orders needs; a\n"
         "target set at a bar's close fills at the next bar's open.\n\n"
         "Parameters\n"
         "----------\n"
         "symbol : str\n"
         "    One of the replay's symbols.\n"
         "quantity : int\n"
         "    The shares to hold; 0 closes the position.\n\n"
         "Raises\n"
         "------\n"
         "ValueError\n"
         "    If the symbol is not one of the replay's.\n")
    .def("position", &Context::position, "symbol"_a,
         "The net quantity held of a symbol.\n\n"
         "Parameters\n"
         "----------\n"
         "symbol : str\n"
         "    One of the replay's symbols.\n\n"
         "Returns\n"
         "-------\n"
         "float\n"
         "    Shares held, 0 when none.\n")
    .def("cash", &Context::cash,
         "Cash in the replay's currency (KRW).\n\n"
         "Returns\n"
         "-------\n"
         "float or None\n"
         "    The cash, or None if none is recorded.\n");
}
