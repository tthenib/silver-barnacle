"""Canonical market data contracts.

Every observation preserves its provider identity, retrieval time, and a
content hash, and carries an explicit eligibility state. Nothing downstream
may consume a bar whose eligibility is below the purpose at hand.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quant_platform.core.metadata import content_hash


class DataEligibility(StrEnum):
    """What a validated observation may be used for (ordered, strictest last).

    ``VALID_FOR_LIVE`` is unreachable for synthetic or single-source data;
    it requires cross-source verification, which is not yet implemented.
    """

    QUARANTINED = "QUARANTINED"
    VALID_FOR_RESEARCH = "VALID_FOR_RESEARCH"
    VALID_FOR_BACKTEST = "VALID_FOR_BACKTEST"
    VALID_FOR_LIVE = "VALID_FOR_LIVE"
    EXPIRED = "EXPIRED"


#: Eligibility ranking used to answer "is X usable for purpose Y".
_ELIGIBILITY_RANK = {
    DataEligibility.QUARANTINED: 0,
    DataEligibility.EXPIRED: 0,
    DataEligibility.VALID_FOR_RESEARCH: 1,
    DataEligibility.VALID_FOR_BACKTEST: 2,
    DataEligibility.VALID_FOR_LIVE: 3,
}


def eligibility_satisfies(actual: DataEligibility, required: DataEligibility) -> bool:
    """True if data with eligibility ``actual`` may serve purpose ``required``."""
    return _ELIGIBILITY_RANK[actual] >= _ELIGIBILITY_RANK[required]


class MarketBar(BaseModel):
    """One daily OHLCV bar in canonical form.

    Prices are adjusted according to ``adjustment_policy`` (currently only
    ``"unadjusted"`` or ``"split_adjusted"`` are produced by our providers);
    the policy travels with the data so consumers never have to guess.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=1)
    trading_day: date
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    source: str
    ingested_at_utc: datetime
    adjustment_policy: str = "unadjusted"

    @model_validator(mode="after")
    def _check_ohlc_consistency(self) -> MarketBar:
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError(
                f"inconsistent OHLC for {self.symbol} {self.trading_day}: "
                f"open/close must lie within [low, high]"
            )
        return self

    def fingerprint(self) -> str:
        """Content hash over the price fields (identity excludes ingestion time)."""
        return content_hash(
            {
                "symbol": self.symbol,
                "trading_day": self.trading_day.isoformat(),
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "close": self.close,
                "volume": self.volume,
                "adjustment_policy": self.adjustment_policy,
            }
        )


class ValidatedSeries(BaseModel):
    """A validated per-symbol daily series with its eligibility verdict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    bars: tuple[MarketBar, ...]
    eligibility: DataEligibility
    quality_score: float = Field(ge=0.0, le=1.0)
    validation_report_id: str
