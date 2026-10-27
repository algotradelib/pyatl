// One replay: the engine, the bars fed to it in order, and its result. The only header that includes the engine.
#pragma once

#include <pyatl/adapters.hpp>
#include <pyatl/series.hpp>

#include <algotradelib/backtest>

#include <nanobind/nanobind.h>

#include <memory>
#include <optional>
#include <algorithm>
#include <queue>
#include <tuple>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace pyatl {

namespace nb = nanobind;

/** What a run produced, in plain types for the Python side. */
struct Result {
  std::size_t bars{0};
  std::vector<std::int64_t> fill_time;
  std::vector<std::string> fill_symbol, fill_side;
  std::vector<double> fill_quantity, fill_price, fill_commission, fill_tax, fill_slippage;
  std::vector<std::int64_t> equity_time;
  std::vector<double> equity;
  std::string opening_equity, closing_equity;
  std::optional<std::string> halted;
  double total_return{NAN}, sharpe{NAN}, annualized_sharpe{NAN}, max_drawdown{NAN};
  double sortino{NAN}, turnover{NAN}, commission_paid{NAN}, tax_paid{NAN}, slippage_paid{NAN};
  std::vector<std::string> rejected_symbol, rejected_reason;
  std::vector<std::string> refused_symbol, refused_reason;
  std::vector<double> refused_limit, refused_attempted;
  std::size_t unfilled{0}, gaps{0}, unvalued_bars{0};
  double lowest_cash{NAN};
};

inline double to_double_or_nan(const std::optional<atl::Decimal64>& value) { return value ? to_double(*value) : NAN; }

/** Bars in the order they are to be fed, converted and checked before the first one is. */
struct Block {
  std::vector<std::size_t> symbol;  // index into the replay's symbols
  std::vector<atl::Bar> bars;
  std::vector<TimePoint> ends;  // bar_period_end of each bar
};

template <class Engine>
Result result_of(const Engine& engine, atl::BarInterval interval) {
  Result out;
  const auto& result = engine.result();
  out.bars = result.bars_;
  for (const auto& execution : result.executions_) {
    const auto& fill = execution.fill_;
    out.fill_time.push_back(to_ns(fill.at_));
    out.fill_symbol.push_back(fill.instrument_.symbol_);
    out.fill_side.push_back(fill.side_ == atl::OrderSide::BUY ? "buy" : "sell");
    out.fill_quantity.push_back(to_double(fill.quantity_));
    out.fill_price.push_back(to_double(fill.price_));
    out.fill_commission.push_back(to_double(execution.commission_));
    out.fill_tax.push_back(to_double(execution.tax_));
    out.fill_slippage.push_back(to_double(execution.slippage_));
  }
  for (const auto& rejection : result.rejected_) {
    out.rejected_symbol.push_back(rejection.instrument_.symbol_);
    out.rejected_reason.emplace_back(atl::strategy::reject_reason_name(rejection.reason_));
  }
  for (const auto& refusal : result.refused_) {
    out.refused_symbol.push_back(refusal.instrument_.symbol_);
    out.refused_reason.emplace_back(atl::strategy::guard_reason_name(refusal.reason_));
    out.refused_limit.push_back(to_double_or_nan(refusal.limit_));
    out.refused_attempted.push_back(to_double_or_nan(refusal.attempted_));
  }
  out.unfilled = result.unfilled_;
  out.gaps = result.gaps_;
  out.unvalued_bars = result.unvalued_bars_;
  if (result.lowest_cash_) out.lowest_cash = to_double(result.lowest_cash_->amount_);
  for (const auto& point : result.equity_) {
    out.equity_time.push_back(to_ns(point.at_));
    out.equity.push_back(to_double(point.equity_));
  }
  if (result.halted_) out.halted = result.halted_->message_;
  // The costs are known from the executions alone, so they are read even when no equity point could be valued;
  // the figures of the curve only when it has a point.
  const auto periods = atl::backtest::periods_per_year(interval, market::session(), market::trading_days);
  const auto report = atl::backtest::summarize(result, engine.fills(), periods);
  out.commission_paid = to_double_or_nan(report.commission_paid_);
  out.tax_paid = to_double_or_nan(report.tax_paid_);
  out.slippage_paid = to_double_or_nan(report.slippage_paid_);
  if (!result.equity_.empty()) {
    out.opening_equity = report.opening_equity_.str();
    out.closing_equity = report.closing_equity_.str();
    out.total_return = report.total_return_;
    out.sharpe = report.sharpe_;
    out.annualized_sharpe = report.annualized_sharpe_;
    out.max_drawdown = report.max_drawdown_;
    out.sortino = report.sortino_;
    out.turnover = report.total_turnover_;
  }
  return out;
}

/** The engine behind one of the two adapters, so a replay holds either through one type. */
class EngineBase {
public:
  virtual ~EngineBase() = default;
  virtual void feed(const atl::strategy::BarEvent& event) = 0;
  virtual Result finish(atl::BarInterval interval) = 0;
};

template <class Strategy>
class EngineOf final : public EngineBase {
public:
  EngineOf(Strategy strategy, atl::backtest::ReplayConfig config, atl::backtest::NextBarFillModel fills)
  : engine_(std::move(strategy), std::move(config), std::move(fills)) {}

  void feed(const atl::strategy::BarEvent& event) override { engine_.feed(event); }

  Result finish(atl::BarInterval interval) override {
    engine_.finish();
    return result_of(engine_, interval);
  }

private:
  atl::backtest::Backtester<Strategy> engine_;
};

/**
 * One run, fed by its owner in as many calls as it likes, then finished once.
 *
 * Every feed is checked whole before its first bar reaches the engine, so a refused feed changes nothing. An
 * exception from the strategy or the engine marks the replay failed; a feed or finish from inside one of its own
 * handlers is refused. Neither copied nor moved: the strategy's context points at `ids_`.
 */
class Replay {
public:
  Replay(nb::handle strategy, const std::vector<std::string>& symbols, const Settings& settings,
         const std::string& interval, const std::string& stamp)
  : interval_(parse_interval(interval)), stamp_(parse_stamp(stamp)) {
    if (nb::hasattr(strategy, "on_start")) {
      // The library's replay never calls on_start; a setup step that silently never runs is worse than none.
      throw nb::type_error("on_start is not called by algotradelib's replay; do the setup in __init__");
    }
    atl::backtest::ReplayConfig config;
    config.cash_ = atl::Decimal64::parse(settings.cash);
    config.currency_ = market::currency();
    config.limits_.permitted_phases_ = std::nullopt;
    for (const auto& symbol : symbols) {
      if (!ids_.emplace(symbol, market::instrument_of(symbol)).second) {
        throw std::invalid_argument("symbol given twice: " + symbol);
      }
      index_.emplace(symbol, symbols_.size());
      symbols_.push_back(symbol);
      by_index_.push_back(market::instrument_of(symbol));
      config.instruments_.push_back(market::reference_of(symbol));
    }
    last_.resize(symbols_.size());
    const auto fills = atl::backtest::NextBarFillModel(
      atl::backtest::CommissionModel::of(atl::Decimal64::parse(settings.commission), atl::Decimal64::parse(settings.min_commission)),
      atl::backtest::SlippageModel::of_ticks(settings.slippage_ticks)
    ).with_sell_tax(atl::backtest::SellTax{atl::Decimal64::parse(settings.sell_tax), market::country});

    handlers_ = std::make_unique<Handlers>(strategy, ids_, market::currency());
    const bool bar = !handlers_->on_bar.is_none(), bars = !handlers_->on_bars.is_none();
    if (bar == bars) {
      throw nb::type_error(bar ? "a strategy defines on_bar or on_bars, not both: on_bar receives each bar, "
                                 "on_bars every instrument's bar for a period at once"
                               : "a strategy must define on_bar(ctx, bar) or on_bars(ctx, bars)");
    }
    if (bar) {
      engine_ = std::make_unique<EngineOf<PyOnBar>>(PyOnBar{{handlers_.get()}}, std::move(config), fills);
    } else {
      engine_ = std::make_unique<EngineOf<PyOnBars>>(PyOnBars{{handlers_.get()}}, std::move(config), fills);
    }
  }

  Replay(const Replay&) = delete;
  Replay& operator=(const Replay&) = delete;

  ~Replay() { release(); }

  const std::vector<std::string>& symbols() const noexcept { return symbols_; }

  /** Feeds whole series, merged by period end; ties go to the earlier symbol in `symbols()`. */
  void feed_series(const std::vector<Series>& all) {
    require_open();
    std::vector<std::size_t> symbol_of(all.size());
    std::vector<bool> seen(symbols_.size(), false);
    std::optional<TimePoint> first;
    for (std::size_t k = 0; k < all.size(); ++k) {
      const auto& series = all[k];
      if (series.interval != interval_ || series.stamp != stamp_) {
        throw std::invalid_argument(series.symbol + ": its interval or stamp differs from the replay's");
      }
      const auto at = index_.find(series.symbol);
      if (at == index_.end()) throw std::invalid_argument("unknown symbol: " + series.symbol);
      if (seen[at->second]) throw std::invalid_argument("symbol given twice: " + series.symbol);
      seen[at->second] = true;
      symbol_of[k] = at->second;
      if (series.bars.empty()) continue;
      // Within a series, make_series ordered the bars and refused a repeated period.
      if (!later_than(last_[at->second], series.ends.front(), series.bars.front().timestamp_)) {
        throw std::invalid_argument(series.symbol + ": its first bar is not later than the last bar fed for it");
      }
      if (!first || series.ends.front() < *first) first = series.ends.front();
    }
    if (first && !not_before(last_fed_, *first)) {
      throw std::invalid_argument("the earliest bar given ends before the last bar fed");
    }

    run([&] { merge(all, symbol_of); });
  }

  /** Feeds a block in its own order, after checking it whole. */
  void feed_block(const Block& block) {
    require_open();
    check_order(block);
    run([&] {
      for (std::size_t i = 0; i < block.bars.size(); ++i) {
        feed_one(block.symbol[i], block.bars[i], block.ends[i]);
      }
    });
  }

  Result finish() {
    require_open();
    Result result;
    run([&] { result = engine_->finish(interval_); });
    state_ = State::FINISHED;
    release();
    return result;
  }

  std::size_t symbol_count() const noexcept { return symbols_.size(); }

  atl::BarInterval interval() const noexcept { return interval_; }

  atl::BarStamp stamp() const noexcept { return stamp_; }

  /** Calls `visit` on every Python object the replay keeps (for the garbage collector). */
  template <class Visit>
  int traverse(Visit visit) const {
    if (!handlers_) return 0;
    for (const auto* object : {&handlers_->ctx_obj, &handlers_->bar_obj, &handlers_->on_bar, &handlers_->on_bars,
                               &handlers_->on_stop}) {
      if (const int status = visit(object->ptr())) return status;
    }
    for (const auto& object : handlers_->slice_pool) {
      if (const int status = visit(object.ptr())) return status;
    }
    return 0;
  }

  /** Drops the engine and the strategy's handlers; every later call raises. For the garbage collector. */
  void clear() {
    if (state_ == State::FEEDING) return;
    if (state_ == State::OPEN) state_ = State::CLEARED;
    release();
  }

private:
  enum class State { OPEN, FEEDING, FINISHED, FAILED, CLEARED };

  struct Last {
    TimePoint end;
    TimePoint time;
  };

  void require_open() const {
    switch (state_) {
      case State::OPEN:
        return;
      case State::FEEDING:
        throw std::runtime_error("a replay cannot be fed or finished from inside its own strategy handler");
      case State::FINISHED:
        throw std::runtime_error("this replay has finished");
      case State::FAILED:
        throw std::runtime_error("this replay failed: " + failure_);
      case State::CLEARED:
        throw std::runtime_error("this replay was cleared by the garbage collector");
    }
  }

  // Feeds every series' bars by period end; ties go to the earlier symbol, the order a stable sort by period end
  // of the series in symbol order gives. Bars of a period usually come from every series (shared dates), so each
  // step scans the heads in symbol order and feeds those at the earliest end; when steps feed few of many heads,
  // the rest goes through a heap, so the cost stays O(n log k).
  void merge(const std::vector<Series>& all, const std::vector<std::size_t>& symbol_of) {
    std::vector<std::size_t> active;
    for (std::size_t k = 0; k < all.size(); ++k) {
      if (!all[k].bars.empty()) active.push_back(k);
    }
    std::sort(active.begin(), active.end(), [&](std::size_t a, std::size_t b) { return symbol_of[a] < symbol_of[b]; });
    std::vector<std::size_t> next(all.size(), 0);
    std::size_t scanned = 0, fed = 0;
    while (!active.empty()) {
      if (scanned > 4 * fed + 4096) break;
      auto earliest = all[active.front()].ends[next[active.front()]];
      for (const auto k : active) earliest = std::min(earliest, all[k].ends[next[k]]);
      scanned += active.size();
      std::size_t kept = 0;
      for (const auto k : active) {
        if (all[k].ends[next[k]] == earliest) {
          feed_one(symbol_of[k], all[k].bars[next[k]], earliest);
          ++next[k];
          ++fed;
        }
        if (next[k] < all[k].bars.size()) active[kept++] = k;
      }
      active.resize(kept);
    }
    // (period end, symbol index, series position): the smallest first.
    using Head = std::tuple<TimePoint, std::size_t, std::size_t>;
    std::priority_queue<Head, std::vector<Head>, std::greater<Head>> heads;
    for (const auto k : active) heads.emplace(all[k].ends[next[k]], symbol_of[k], k);
    while (!heads.empty()) {
      const auto [end, symbol, k] = heads.top();
      heads.pop();
      feed_one(symbol, all[k].bars[next[k]], end);
      if (++next[k] < all[k].bars.size()) heads.emplace(all[k].ends[next[k]], symbol, k);
    }
  }

  // The order rules, the library's own for on_bars (which it does not check for on_bar): each symbol's bars
  // strictly later than its previous one, by period end and by time, and period ends never decreasing across the
  // replay. feed_series and check_order both decide through these two.
  static bool later_than(const std::optional<Last>& last, TimePoint end, TimePoint time) {
    return !last || (last->end < end && last->time < time);
  }

  static bool not_before(const std::optional<TimePoint>& previous, TimePoint end) {
    return !previous || !(end < *previous);
  }

  void check_order(const Block& block) const {
    auto last = last_;
    auto previous = last_fed_;
    for (std::size_t i = 0; i < block.bars.size(); ++i) {
      const auto end = block.ends[i];
      const auto time = block.bars[i].timestamp_;
      auto& mine = last[block.symbol[i]];
      if (!later_than(mine, end, time)) {
        throw std::invalid_argument("row " + std::to_string(i) + ": " + symbols_[block.symbol[i]] +
                                    " is not later than its previous bar");
      }
      if (!not_before(previous, end)) {
        throw std::invalid_argument("row " + std::to_string(i) + " ends before the bar fed before it");
      }
      mine = Last{end, time};
      previous = end;
    }
  }

  void feed_one(std::size_t symbol, const atl::Bar& bar, TimePoint end) {
    engine_->feed(atl::strategy::make_bar_event(by_index_[symbol], interval_, stamp_, bar));
    last_[symbol] = Last{end, bar.timestamp_};
    last_fed_ = end;
  }

  template <class Body>
  void run(Body body) {
    state_ = State::FEEDING;
    try {
      body();
    } catch (nb::python_error& error) {
      fail();
      failure_ = describe(error);
      throw;
    } catch (const std::exception& error) {
      fail();
      failure_ = error.what();
      throw;
    } catch (...) {
      fail();
      failure_ = "an unknown error";
      throw;
    }
    state_ = State::OPEN;
  }

  void fail() noexcept {
    state_ = State::FAILED;
    release();
  }

  // The exception's type and message, not the traceback its what() carries. Best effort: formatting runs Python
  // (a __str__ may raise), and the replay is already failed and released whatever it says.
  static std::string describe(nb::python_error& error) noexcept {
    try {
      return std::string(nb::type_name(error.type()).c_str()) + ": " + nb::str(error.value()).c_str();
    } catch (...) {
    }
    try {
      return std::string(nb::type_name(error.type()).c_str());
    } catch (...) {
    }
    return "a Python exception";
  }

  // The engine first: it holds the adapters, which point at the handlers.
  void release() noexcept {
    engine_.reset();
    handlers_.reset();
  }

  atl::BarInterval interval_;
  atl::BarStamp stamp_;
  std::vector<std::string> symbols_;
  std::unordered_map<std::string, atl::InstrumentId> ids_;
  std::unordered_map<std::string, std::size_t> index_;
  std::vector<atl::InstrumentId> by_index_;
  std::vector<std::optional<Last>> last_;
  std::optional<TimePoint> last_fed_;
  std::unique_ptr<Handlers> handlers_;
  std::unique_ptr<EngineBase> engine_;
  State state_{State::OPEN};
  std::string failure_;
};

} // namespace pyatl
