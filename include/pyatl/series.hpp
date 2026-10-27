// Bar series, replay settings and pyatl's market: what a replay is given. Includes the library's strategy types
// (for period ends) but not the engine, so a file that builds series does not compile the replay.
#pragma once

#include <algotradelib/analytics>
#include <algotradelib/core>
#include <algotradelib/strategy>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace pyatl {

namespace atl = algotradelib;

using TimePoint = std::chrono::system_clock::time_point;

/**
 * What pyatl decides itself, in one place: every symbol is a KRX stock in KRW, sales pay Korea's tax, and
 * returns are annualized over the KRX session's 245 trading days.
 */
namespace market {

inline atl::Currency currency() { return atl::Currency{"KRW"}; }

inline constexpr atl::Country country = atl::Country::KR;

inline atl::strategy::SessionWindow session() { return atl::strategy::SessionWindow::krx(); }

inline constexpr double trading_days = 245.0;

inline atl::InstrumentId instrument_of(const std::string& symbol) {
  return atl::InstrumentId{country, atl::Venue::COMBINED, symbol};
}

inline atl::Instrument reference_of(const std::string& symbol) {
  atl::Instrument instrument;
  instrument.id_ = instrument_of(symbol);
  instrument.name_ = symbol;
  instrument.type_ = atl::SecurityType::STOCK;
  instrument.currency_ = currency();
  instrument.lot_size_ = atl::Decimal64(1, 0);
  instrument.price_rule_ = atl::PriceRule::krx_equity();
  return instrument;
}

} // namespace market

/** One instrument's bars in time order, converted to the library's types when built, with their period ends. */
struct Series {
  std::string symbol;
  atl::BarInterval interval{atl::BarInterval::ONE_DAY};
  atl::BarStamp stamp{atl::BarStamp::OPEN};
  std::vector<atl::Bar> bars;
  std::vector<TimePoint> ends;  // bar_period_end of each bar, increasing
};

/** Costs and starting cash, as decimal strings (exact). */
struct Settings {
  std::string cash{"100000000"};
  std::string commission{"0"};
  std::string min_commission{"0"};
  std::string sell_tax{"0"};
  int slippage_ticks{0};
};

inline atl::BarInterval parse_interval(const std::string& text) {
  for (const auto interval : atl::all_bar_intervals) {
    if (atl::bar_interval_name(interval) == text) return interval;
  }
  std::string names;
  for (const auto interval : atl::all_bar_intervals) {
    names += (names.empty() ? "" : ", ") + std::string(atl::bar_interval_name(interval));
  }
  throw std::invalid_argument("unknown interval '" + text + "' (" + names + ")");
}

inline atl::BarStamp parse_stamp(const std::string& text) {
  if (text == "open") return atl::BarStamp::OPEN;
  if (text == "close") return atl::BarStamp::CLOSE;
  throw std::invalid_argument("stamp is 'open' (the time is the period's start) or 'close' (its end)");
}

inline TimePoint from_ns(std::int64_t ns) {
  return TimePoint{std::chrono::duration_cast<TimePoint::duration>(std::chrono::nanoseconds(ns))};
}

inline atl::Decimal64 exact(double value, std::uint8_t scale, const char* field, std::size_t row) {
  const auto decimal = atl::analytics::to_decimal(value, scale);
  if (!decimal) {
    throw std::invalid_argument(std::string(field) + " at row " + std::to_string(row) + " is not a representable decimal");
  }
  return *decimal;
}

inline std::uint8_t checked_scale(int scale) {
  if (scale < 0 || scale > 18) throw std::invalid_argument("scale is 0 to 18");
  return static_cast<std::uint8_t>(scale);
}

/** One row as a bar; an open of NaN means the source has none. */
inline atl::Bar bar_of(std::int64_t time, double open, double high, double low, double close, double volume,
                       std::uint8_t scale, std::size_t row) {
  atl::Bar bar;
  bar.timestamp_ = from_ns(time);
  if (!std::isnan(open)) bar.open_ = exact(open, scale, "open", row);
  bar.high_ = exact(high, scale, "high", row);
  bar.low_ = exact(low, scale, "low", row);
  bar.close_ = exact(close, scale, "close", row);
  bar.volume_ = exact(volume, scale, "volume", row);
  return bar;
}

/**
 * Puts a series in time order and fills its period ends. Rows given out of order are sorted (stably, and only
 * when needed); two rows of the symbol with the same period end are refused, naming both input rows.
 */
inline void order_series(Series& series) {
  const auto n = series.bars.size();
  std::vector<std::size_t> rows(n);
  std::iota(rows.begin(), rows.end(), std::size_t{0});
  const auto earlier = [&series](std::size_t a, std::size_t b) {
    return series.bars[a].timestamp_ < series.bars[b].timestamp_;
  };
  if (!std::is_sorted(rows.begin(), rows.end(), earlier)) {
    std::stable_sort(rows.begin(), rows.end(), earlier);
    std::vector<atl::Bar> sorted;
    sorted.reserve(n);
    for (const auto row : rows) sorted.push_back(series.bars[row]);
    series.bars = std::move(sorted);
  }
  series.ends.clear();
  series.ends.reserve(n);
  for (std::size_t i = 0; i < n; ++i) {
    series.ends.push_back(atl::strategy::bar_period_end(series.bars[i], series.interval, series.stamp));
    if (i > 0 && !(series.ends[i - 1] < series.ends[i])) {
      throw std::invalid_argument(series.symbol + ": rows " + std::to_string(rows[i - 1]) + " and " +
                                  std::to_string(rows[i]) + " are bars for the same period");
    }
  }
}

} // namespace pyatl
