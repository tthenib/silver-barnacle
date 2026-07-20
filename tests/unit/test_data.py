"""Data plane: validation verdicts, point-in-time store discipline."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from quant_platform.core.errors import DataValidationError
from quant_platform.data.contracts import DataEligibility, MarketBar
from quant_platform.data.store import MarketDataStore
from quant_platform.data.synthetic import SyntheticMarketDataProvider
from quant_platform.data.validation import BarSeriesValidator
from tests.conftest import make_bar


def weekday_series(
    count: int, start: date = date(2025, 1, 6), close: float = 100.0
) -> list[MarketBar]:
    bars = []
    day = start
    price = close
    while len(bars) < count:
        if day.weekday() < 5:
            bars.append(make_bar(trading_day=day, close=price))
            price *= 1.001
        day += timedelta(days=1)
    return bars


class TestBarContract:
    def test_inconsistent_ohlc_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_bar(close=100.0, high=90.0, low=95.0)

    def test_fingerprint_excludes_ingestion_time(self) -> None:
        a = make_bar()
        b = a.model_copy(update={"ingested_at_utc": a.ingested_at_utc + timedelta(days=1)})
        assert a.fingerprint() == b.fingerprint()


class TestValidator:
    def test_clean_series_is_backtest_eligible(self) -> None:
        series, report = BarSeriesValidator().validate("AAA", weekday_series(60))
        assert series.eligibility is DataEligibility.VALID_FOR_BACKTEST
        assert report.quality_score == 1.0
        assert not report.failed_checks()

    def test_duplicate_days_quarantine(self) -> None:
        bars = weekday_series(60)
        bars.append(bars[-1])
        series, report = BarSeriesValidator().validate("AAA", bars)
        assert series.eligibility is DataEligibility.QUARANTINED
        assert any(c.name == "no_duplicate_days" for c in report.failed_checks())

    def test_long_gap_caps_at_research(self) -> None:
        bars = weekday_series(40)
        late = weekday_series(20, start=bars[-1].trading_day + timedelta(days=30))
        series, report = BarSeriesValidator().validate("AAA", bars + late)
        assert series.eligibility is DataEligibility.VALID_FOR_RESEARCH
        assert any(c.name == "calendar_gaps" for c in report.failed_checks())

    def test_implausible_return_caps_at_research(self) -> None:
        bars = weekday_series(60)
        spike_day = bars[-1].trading_day + timedelta(days=1)
        bars.append(make_bar(trading_day=spike_day, close=bars[-1].close * 3))
        series, report = BarSeriesValidator().validate("AAA", bars)
        assert series.eligibility is DataEligibility.VALID_FOR_RESEARCH
        assert any(c.name == "return_plausibility" for c in report.failed_checks())

    def test_short_history_caps_at_research(self) -> None:
        series, _ = BarSeriesValidator().validate("AAA", weekday_series(10))
        assert series.eligibility is DataEligibility.VALID_FOR_RESEARCH

    def test_empty_series_quarantined(self) -> None:
        series, _ = BarSeriesValidator().validate("AAA", [])
        assert series.eligibility is DataEligibility.QUARANTINED


class TestStore:
    def test_refuses_underqualified_data(self) -> None:
        store = MarketDataStore(required_eligibility=DataEligibility.VALID_FOR_BACKTEST)
        series, _ = BarSeriesValidator().validate("AAA", weekday_series(10))  # research-only
        with pytest.raises(DataValidationError):
            store.add(series)

    def test_as_of_never_returns_future_bars(self) -> None:
        store = MarketDataStore(required_eligibility=DataEligibility.VALID_FOR_BACKTEST)
        series, _ = BarSeriesValidator().validate("AAA", weekday_series(60))
        store.add(series)
        cutoff = series.bars[30].trading_day
        history = store.bars_as_of("AAA", cutoff)
        assert history[-1].trading_day == cutoff
        assert all(b.trading_day <= cutoff for b in history)


class TestSyntheticProvider:
    def test_deterministic_for_same_seed(self) -> None:
        a = SyntheticMarketDataProvider(seed=7).get_daily_bars(
            "AAA", date(2025, 1, 1), date(2025, 3, 1)
        )
        b = SyntheticMarketDataProvider(seed=7).get_daily_bars(
            "AAA", date(2025, 1, 1), date(2025, 3, 1)
        )
        assert [x.fingerprint() for x in a] == [y.fingerprint() for y in b]

    def test_different_symbols_differ(self) -> None:
        provider = SyntheticMarketDataProvider(seed=7)
        a = provider.get_daily_bars("AAA", date(2025, 1, 1), date(2025, 2, 1))
        b = provider.get_daily_bars("BBB", date(2025, 1, 1), date(2025, 2, 1))
        assert [x.close for x in a] != [y.close for y in b]
