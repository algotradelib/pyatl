// One function per binding file; module.cpp calls each.
#pragma once

#include <nanobind/nanobind.h>

namespace pyatl {

/** Bar and Context: what a strategy handler receives (types.cpp). */
void bind_types(nanobind::module_& m);

/** Series, make_series and Settings: what a backtest is given (series.cpp). */
void bind_series(nanobind::module_& m);

/** run_backtest: the replay (backtest.cpp). */
void bind_backtest(nanobind::module_& m);

} // namespace pyatl
