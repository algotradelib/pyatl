// Bar series and replay settings: what a backtest is given. Needs only the library's core types, so a
// file that builds series does not compile the engine.
#pragma once

#include <algotradelib/core>

#include <stdexcept>
#include <string>
#include <vector>

namespace pyatl {

namespace atl = algotradelib;

/** One instrument's bars, converted to the library's types when built. */
struct Series {
  std::string symbol;
  atl::BarInterval interval{atl::BarInterval::ONE_DAY};
  atl::BarStamp stamp{atl::BarStamp::OPEN};
  std::vector<atl::Bar> bars;
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

// TODO(market): every instrument is a KRX stock in KRW for now.
inline atl::InstrumentId instrument_of(const std::string& symbol) {
  return atl::InstrumentId{atl::Country::KR, atl::Venue::COMBINED, symbol};
}

inline atl::Instrument reference_of(const std::string& symbol) {
  atl::Instrument instrument;
  instrument.id_ = instrument_of(symbol);
  instrument.name_ = symbol;
  instrument.type_ = atl::SecurityType::STOCK;
  instrument.currency_ = atl::Currency{"KRW"};
  instrument.lot_size_ = atl::Decimal64(1, 0);
  instrument.price_rule_ = atl::PriceRule::krx_equity();
  return instrument;
}

} // namespace pyatl
