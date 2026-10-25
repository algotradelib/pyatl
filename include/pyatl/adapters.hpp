// The C++ strategies the library runs, each forwarding to a duck-typed Python object.
//
// The library detects handlers at compile time and refuses a strategy that declares both on_bar and
// on_bars, so there is one adapter per bar handler, chosen by what the Python class defines. on_stop is
// always declared and calls Python only if the class defines it. on_start is not offered: no driver the
// library ships calls it (run_backtest refuses a class that defines it).
//
// The GIL is held for the whole replay: taking it per call costs ~50 ns and collapses under threads.
#pragma once

#include <pyatl/views.hpp>

#include <nanobind/nanobind.h>

#include <vector>

namespace pyatl {

namespace nb = nanobind;

/** The Python objects one run hands to every call. Owned by the caller, outlives the engine. */
struct Handlers {
  nb::object ctx_obj;
  Context* ctx;
  nb::object bar_obj;
  Bar* bar;
  std::vector<nb::object> slice_pool;  // on_bars: one bar object per instrument, reused
  std::vector<Bar*> slice_ptrs;
  nb::object on_bar, on_bars, on_stop;  // None when the class lacks it

  explicit Handlers(nb::handle strategy, const std::unordered_map<std::string, atl::InstrumentId>& ids, atl::Currency currency) {
    ctx_obj = nb::cast(Context(&ids, std::move(currency)));
    ctx = nb::inst_ptr<Context>(ctx_obj);
    bar_obj = nb::cast(Bar{});
    bar = nb::inst_ptr<Bar>(bar_obj);
    auto method = [&](const char* name) { return nb::hasattr(strategy, name) ? nb::object(strategy.attr(name)) : nb::none(); };
    on_bar = method("on_bar");
    on_bars = method("on_bars");
    on_stop = method("on_stop");
  }
};

/** Binds the context for one call and unbinds it however the call ends. */
class Bound {
public:
  template <class Ctx>
  Bound(Handlers& h, Ctx& ctx) : h_(h) { h_.ctx->bind(ctx); }
  ~Bound() { h_.ctx->unbind(); }
  Bound(const Bound&) = delete;
  Bound& operator=(const Bound&) = delete;

private:
  Handlers& h_;
};

struct LifecycleHandlers {
  Handlers* h;

  template <class Ctx>
  void on_stop(Ctx& ctx) {
    if (h->on_stop.is_none()) return;
    Bound bound(*h, ctx);
    h->on_stop(h->ctx_obj);
  }
};

/** on_bar(ctx, bar): one call per bar. */
struct PyOnBar : LifecycleHandlers {
  static constexpr bool reads_bar_history = false;

  template <class Ctx>
  void on_bar(Ctx& ctx, const atl::strategy::BarEvent& event) {
    Bound bound(*h, ctx);
    h->bar->fill(event);
    h->on_bar(h->ctx_obj, h->bar_obj);
  }
};

/** on_bars(ctx, bars): one call per period end, every instrument's bar for it in a list. */
struct PyOnBars : LifecycleHandlers {
  static constexpr bool reads_bar_history = false;

  template <class Ctx>
  void on_bars(Ctx& ctx, const atl::strategy::BarSlice& slice) {
    Bound bound(*h, ctx);
    auto& pool = h->slice_pool;
    while (pool.size() < slice.bars_.size()) {
      pool.push_back(nb::cast(Bar{}));
      h->slice_ptrs.push_back(nb::inst_ptr<Bar>(pool.back()));
    }
    nb::list bars;
    for (std::size_t i = 0; i < slice.bars_.size(); ++i) {
      h->slice_ptrs[i]->fill(slice.bars_[i]);
      bars.append(pool[i]);
    }
    h->on_bars(h->ctx_obj, bars);
  }
};

} // namespace pyatl
