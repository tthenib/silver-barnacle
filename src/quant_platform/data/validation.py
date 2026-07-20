"""Deterministic market data validation.

The validator runs a fixed sequence of named checks over a per-symbol daily
series and produces a :class:`ValidationReport` listing every check with its
outcome. Critical failures quarantine the series; softer defects (e.g. long
gaps) cap eligibility at research use. The validator never repairs data
silently — imputation is a policy decision, not a default.
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field

from quant_platform.core.metadata import new_id
from quant_platform.data.contracts import DataEligibility, MarketBar, ValidatedSeries


class CheckSeverity(StrEnum):
    CRITICAL = "CRITICAL"  # failure quarantines the series
    MAJOR = "MAJOR"  # failure caps eligibility at VALID_FOR_RESEARCH
    MINOR = "MINOR"  # failure lowers the quality score only


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    severity: CheckSeverity
    passed: bool
    detail: str = ""


class ValidationConfig(BaseModel):
    """Tunable validation thresholds (versioned with the config tree)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_calendar_gap_days: int = Field(default=5, gt=0)
    max_abs_daily_return: float = Field(default=0.5, gt=0)
    min_bars_for_backtest: int = Field(default=30, gt=0)


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    report_id: str
    symbol: str
    checks: tuple[CheckResult, ...]
    eligibility: DataEligibility
    quality_score: float = Field(ge=0.0, le=1.0)

    def failed_checks(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


class BarSeriesValidator:
    """Validates one symbol's daily bars and assigns eligibility."""

    def __init__(self, config: ValidationConfig | None = None) -> None:
        self._config = config or ValidationConfig()

    def validate(
        self, symbol: str, bars: list[MarketBar]
    ) -> tuple[ValidatedSeries, ValidationReport]:
        checks = [
            self._check_nonempty(bars),
            self._check_single_symbol(symbol, bars),
            self._check_strictly_increasing_days(bars),
            self._check_no_duplicates(bars),
            self._check_calendar_gaps(bars),
            self._check_return_plausibility(bars),
            self._check_history_depth(bars),
        ]
        eligibility, quality = self._verdict(checks)
        report = ValidationReport(
            report_id=new_id("valreport"),
            symbol=symbol,
            checks=tuple(checks),
            eligibility=eligibility,
            quality_score=quality,
        )
        series = ValidatedSeries(
            symbol=symbol,
            bars=tuple(sorted(bars, key=lambda b: b.trading_day)),
            eligibility=eligibility,
            quality_score=quality,
            validation_report_id=report.report_id,
        )
        return series, report

    def _verdict(self, checks: list[CheckResult]) -> tuple[DataEligibility, float]:
        failed = [c for c in checks if not c.passed]
        if any(c.severity is CheckSeverity.CRITICAL for c in failed):
            return DataEligibility.QUARANTINED, 0.0
        # Quality: fraction of passed checks, weighted against major defects.
        penalty = sum(0.25 if c.severity is CheckSeverity.MAJOR else 0.05 for c in failed)
        quality = max(0.0, 1.0 - penalty)
        if any(c.severity is CheckSeverity.MAJOR for c in failed):
            return DataEligibility.VALID_FOR_RESEARCH, quality
        # VALID_FOR_LIVE additionally requires cross-source verification,
        # which no current provider supports; cap at backtest eligibility.
        return DataEligibility.VALID_FOR_BACKTEST, quality

    def _check_nonempty(self, bars: list[MarketBar]) -> CheckResult:
        return CheckResult(
            name="nonempty",
            severity=CheckSeverity.CRITICAL,
            passed=len(bars) > 0,
            detail="" if bars else "series contains no bars",
        )

    def _check_single_symbol(self, symbol: str, bars: list[MarketBar]) -> CheckResult:
        foreign = sorted({b.symbol for b in bars if b.symbol != symbol})
        return CheckResult(
            name="single_symbol",
            severity=CheckSeverity.CRITICAL,
            passed=not foreign,
            detail=f"unexpected symbols: {foreign}" if foreign else "",
        )

    def _check_strictly_increasing_days(self, bars: list[MarketBar]) -> CheckResult:
        ordered = sorted(bars, key=lambda b: b.trading_day)
        out_of_order = sum(
            1 for given, expected in zip(bars, ordered, strict=True) if given is not expected
        )
        return CheckResult(
            name="monotonic_days",
            severity=CheckSeverity.MINOR,
            passed=out_of_order == 0,
            detail=f"{out_of_order} bars arrived out of order" if out_of_order else "",
        )

    def _check_no_duplicates(self, bars: list[MarketBar]) -> CheckResult:
        days = [b.trading_day for b in bars]
        duplicates = len(days) - len(set(days))
        return CheckResult(
            name="no_duplicate_days",
            severity=CheckSeverity.CRITICAL,
            passed=duplicates == 0,
            detail=f"{duplicates} duplicated trading days" if duplicates else "",
        )

    def _check_calendar_gaps(self, bars: list[MarketBar]) -> CheckResult:
        ordered = sorted(bars, key=lambda b: b.trading_day)
        limit = timedelta(days=self._config.max_calendar_gap_days)
        gaps = [
            (prev.trading_day, cur.trading_day)
            for prev, cur in pairwise(ordered)
            if cur.trading_day - prev.trading_day > limit
        ]
        return CheckResult(
            name="calendar_gaps",
            severity=CheckSeverity.MAJOR,
            passed=not gaps,
            detail=f"gaps beyond {limit.days}d: {gaps[:3]}" if gaps else "",
        )

    def _check_return_plausibility(self, bars: list[MarketBar]) -> CheckResult:
        ordered = sorted(bars, key=lambda b: b.trading_day)
        threshold = self._config.max_abs_daily_return
        outliers = [
            (prev.trading_day, cur.trading_day, cur.close / prev.close - 1.0)
            for prev, cur in pairwise(ordered)
            if abs(cur.close / prev.close - 1.0) > threshold
        ]
        return CheckResult(
            name="return_plausibility",
            severity=CheckSeverity.MAJOR,
            passed=not outliers,
            detail=(
                f"{len(outliers)} daily moves beyond ±{threshold:.0%}; "
                f"possible unadjusted corporate action or bad print"
                if outliers
                else ""
            ),
        )

    def _check_history_depth(self, bars: list[MarketBar]) -> CheckResult:
        needed = self._config.min_bars_for_backtest
        return CheckResult(
            name="history_depth",
            severity=CheckSeverity.MAJOR,
            passed=len(bars) >= needed,
            detail=f"only {len(bars)} bars, {needed} required" if len(bars) < needed else "",
        )
