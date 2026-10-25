// One replay of a Python strategy over bar series. The only header that compiles the engine.
#pragma once

#include <pyatl/adapters.hpp>
#include <pyatl/series.hpp>

#include <algotradelib/backtest>

#include <algorithm>
#include <string>
#include <vector>

namespace pyatl {

/** What a run produced, in plain types for the Python side. */
struct Result {
  std::size_t bars{0};
  // fills, one entry per execution
  std::vector<std::int64_t> fill_time;
  std::vector<std::string> fill_symbol, fill_side;
  std::vector<double> fill_quantity, fill_price, fill_commission;
  // equity at each period end
  std::vector<std::int64_t> equity_time;
  std::vector<double> equity;
  std::string opening_equity, closing_equity;
  std::optional<std::string> halted;
  // the library's summary; NaN where a figure does not exist
  double total_return{NAN}, sharpe{NAN}, annualized_sharpe{NAN}, max_drawdown{NAN};
};

template <class Strategy>
Result replay(Strategy strategy, const std::vector<Series>& all, const Settings& settings) {
  if (all.empty()) throw std::invalid_argument("no series given");
  const auto interval = all.front().interval;

  atl::backtest::ReplayConfig config;
  config.cash_ = atl::Decimal64::parse(settings.cash);
  for (const auto& series : all) config.instruments_.push_back(reference_of(series.symbol));
  // As the library's offline example: no trading calendar, so the phase is never OPEN, and orders are
  // permitted in any phase.
  config.limits_.permitted_phases_ = std::nullopt;

  const auto fills = atl::backtest::NextBarFillModel(
    atl::backtest::CommissionModel::of(atl::Decimal64::parse(settings.commission), atl::Decimal64::parse(settings.min_commission)),
    atl::backtest::SlippageModel::of_ticks(settings.slippage_ticks)
  ).with_sell_tax(atl::backtest::SellTax{atl::Decimal64::parse(settings.sell_tax), atl::Country::KR});

  std::vector<atl::strategy::BarEvent> events;
  for (const auto& series : all) {
    const auto id = instrument_of(series.symbol);
    for (const auto& bar : series.bars) {
      events.push_back(atl::strategy::make_bar_event(id, series.interval, series.stamp, bar));
    }
  }
  std::stable_sort(events.begin(), events.end(), [](const auto& a, const auto& b) { return a.period_end_ < b.period_end_; });

  atl::backtest::Backtester<Strategy> engine(std::move(strategy), config, fills);
  for (const auto& event : events) engine.feed(event);
  engine.finish();

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
  }
  for (const auto& point : result.equity_) {
    out.equity_time.push_back(to_ns(point.at_));
    out.equity.push_back(to_double(point.equity_));
  }
  if (result.halted_) out.halted = result.halted_->message_;
  if (!result.equity_.empty()) {
    const auto periods = atl::backtest::periods_per_year(interval, atl::strategy::SessionWindow::krx(), 245.0);
    const auto report = atl::backtest::summarize(result, engine.fills(), periods);
    out.opening_equity = report.opening_equity_.str();
    out.closing_equity = report.closing_equity_.str();
    out.total_return = report.total_return_;
    out.sharpe = report.sharpe_;
    out.annualized_sharpe = report.annualized_sharpe_;
    out.max_drawdown = report.max_drawdown_;
  }
  return out;
}

} // namespace pyatl
