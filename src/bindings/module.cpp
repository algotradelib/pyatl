// pyatl._core: the bindings. The Python package (src/pyatl) is the public API; this module is its engine.
#include "bindings.hpp"

#include <algotradelib/version>

NB_MODULE(_core, m) {
  m.doc() = "algotradelib's replay, driven by a Python strategy";
  pyatl::bind_types(m);
  pyatl::bind_series(m);
  pyatl::bind_backtest(m);
  m.attr("ALGOTRADELIB_VERSION") = ATL_VERSION_STRING;
}
