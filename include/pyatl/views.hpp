// What a Python strategy sees: a bar of plain numbers and a context. Both are created once per run and
// refilled on every call (a new object per call costs more than the call itself).
#pragma once

#if !defined(ATL_HAS_EIGEN)
#error "pyatl needs algotradelib built with ATL_USE_EIGEN=ON (the default)."
#endif

#include <algotradelib/analytics>
#include <algotradelib/strategy>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <unordered_map>

namespace pyatl {

namespace atl = algotradelib;

inline std::int64_t to_ns(std::chrono::system_clock::time_point at) {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(at.time_since_epoch()).count();
}

inline double to_double(const atl::Decimal64& value) { return atl::analytics::to_scalar(value); }

/** One bar as doubles. `time` is the period end, ns since the epoch (UTC). */
struct Bar {
  std::string symbol;
  std::int64_t time{0};
  double open{NAN}, high{0}, low{0}, close{0}, volume{0};

  void fill(const atl::strategy::BarEvent& event) {
    if (symbol != event.instrument_.symbol_) symbol = event.instrument_.symbol_;
    time = to_ns(event.period_end_);
    open = event.bar_.open_ ? to_double(*event.bar_.open_) : NAN;
    high = to_double(event.bar_.high_);
    low = to_double(event.bar_.low_);
    close = to_double(event.bar_.close_);
    volume = to_double(event.bar_.volume_);
  }
};

/**
 * The running `Context<Tag>`, whose type is a template parameter of every handler, erased behind function
 * pointers that `bind` sets. Valid only during a handler call; outside one every method raises.
 */
class Context {
public:
  explicit Context(const std::unordered_map<std::string, atl::InstrumentId>* ids, atl::Currency currency)
      : ids_(ids), currency_(std::move(currency)) {}

  template <class Ctx>
  void bind(Ctx& ctx) {
    ctx_ = &ctx;
    submit_ = [](void* p, const atl::InstrumentId& id, std::int64_t quantity) {
      atl::strategy::TargetPosition target;
      target.instrument_ = id;
      target.target_quantity_ = atl::Decimal64(quantity, 0);
      target.tag_ = "pyatl";
      static_cast<Ctx*>(p)->submit(std::move(target));
    };
    position_ = [](void* p, const atl::InstrumentId& id) {
      return static_cast<Ctx*>(p)->portfolio().net_quantity_of(id);
    };
    cash_ = [](void* p, const atl::Currency& currency) {
      return static_cast<Ctx*>(p)->portfolio().cash_in(currency);
    };
    now_ = to_ns(ctx.now());
  }

  void unbind() noexcept { ctx_ = nullptr; }

  std::int64_t now() const {
    require_bound();
    return now_;
  }

  /** Asks the runner to hold `quantity` of `symbol`; it sends what the difference needs. */
  void target(const std::string& symbol, std::int64_t quantity) {
    require_bound();
    submit_(ctx_, id_of(symbol), quantity);
  }

  /** The net quantity held. Raises if the snapshot's sum overflowed (never read that as flat). */
  double position(const std::string& symbol) const {
    require_bound();
    const auto held = position_(ctx_, id_of(symbol));
    if (!held) throw std::overflow_error("the position of " + symbol + " overflowed");
    return to_double(*held);
  }

  /** Cash in the replay's currency, or None if none is recorded. */
  std::optional<double> cash() const {
    require_bound();
    const auto amount = cash_(ctx_, currency_);
    if (!amount) return std::nullopt;
    return to_double(*amount);
  }

private:
  void require_bound() const {
    if (ctx_ == nullptr) throw std::logic_error("ctx is valid only inside a strategy handler");
  }

  const atl::InstrumentId& id_of(const std::string& symbol) const {
    const auto found = ids_->find(symbol);
    if (found == ids_->end()) throw std::invalid_argument("unknown symbol: " + symbol);
    return found->second;
  }

  const std::unordered_map<std::string, atl::InstrumentId>* ids_;
  atl::Currency currency_;
  void* ctx_{nullptr};
  void (*submit_)(void*, const atl::InstrumentId&, std::int64_t){nullptr};
  std::optional<atl::Decimal64> (*position_)(void*, const atl::InstrumentId&){nullptr};
  std::optional<atl::Decimal64> (*cash_)(void*, const atl::Currency&){nullptr};
  std::int64_t now_{0};
};

} // namespace pyatl
