"""Shared statistical helpers for the research analyses.

Kept deliberately small and dependency-light. These are properties of estimators,
not of any strategy, so they are stable and can be relied on across analyses.
"""

from __future__ import annotations

import math

from scipy import stats

EULER_MASCHERONI = 0.5772156649015329


def sharpe_standard_error(sharpe: float, years: float) -> float:
    """Lo (2002) asymptotic SE of an annualised Sharpe estimate, iid case.

        SE(S_hat) ~ sqrt((1 + S^2 / 2) / T),  T in years.

    Serial correlation and negative skew both inflate the true SE, so this is a
    *lower bound* on our uncertainty. Every conclusion drawn from it is therefore
    optimistic.
    """
    return math.sqrt((1.0 + sharpe**2 / 2.0) / years)


def expected_max_sharpe_under_null(n_trials: int, se: float) -> float:
    """Expected best in-sample Sharpe from `n_trials` worthless strategies.

    Bailey & Lopez de Prado's expected-maximum approximation for N independent
    trials drawn from N(0, se^2):

        E[max] ~ se * ((1 - g) * z(1 - 1/N) + g * z(1 - 1/(N*e)))

    with g the Euler-Mascheroni constant. This is the number an *edgeless* search
    is expected to produce, and it is the SR_0 benchmark in the Deflated Sharpe
    Ratio.
    """
    if n_trials < 2:
        return 0.0
    z1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return se * ((1.0 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)


def null_sharpe_dispersion(years: float) -> float:
    """SD of annualised Sharpe estimates across trials when no trial has any edge."""
    return math.sqrt(1.0 / years)


def deflated_sharpe(
    observed_sharpe: float,
    n_trials: int,
    years: float,
    obs_per_year: int = 365,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Bailey & Lopez de Prado's Deflated Sharpe Ratio.

    P(true Sharpe > 0), correcting the *selection-sample* estimate for the number
    of trials that produced it, for sample length, and for non-normality:

        DSR = Phi( (sr_hat - sr_0) * sqrt(T - 1)
                   / sqrt(1 - g3*sr_hat + ((g4 - 1)/4) * sr_hat^2) )

    Inputs are annualised for convenience; the formula itself operates on
    per-observation Sharpe, which is what makes the higher-moment correction
    small in practice. Getting that conversion wrong inflates the threshold to
    unreachable levels -- see `results/research_power.md`.

    IMPORTANT: apply this to the sample on which selection occurred (the
    development set). Applying it again to a fresh out-of-sample estimate double
    -counts the penalty: conditional on the strategy, an out-of-sample estimate
    is not selection-biased.

    Defaults assume normal returns. Crypto's negative skew and excess kurtosis
    both push the true DSR *below* what these defaults report.
    """
    n_obs = years * obs_per_year
    scale = math.sqrt(obs_per_year)
    sr_hat = observed_sharpe / scale
    sr_0 = expected_max_sharpe_under_null(n_trials, null_sharpe_dispersion(years)) / scale
    denom = math.sqrt(max(1.0 - skew * sr_hat + ((kurtosis - 1.0) / 4.0) * sr_hat**2, 1e-12))
    return float(stats.norm.cdf((sr_hat - sr_0) * math.sqrt(n_obs - 1.0) / denom))


def deflated_sharpe_threshold(
    n_trials: int,
    years: float,
    confidence: float = 0.95,
    obs_per_year: int = 365,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Minimum observed annualised Sharpe on the SELECTION sample for DSR > `confidence`.

    Solved by fixed-point iteration because the non-normality denominator depends
    on the Sharpe being solved for. Converges in a few steps.
    """
    n_obs = years * obs_per_year
    scale = math.sqrt(obs_per_year)
    sr_0 = expected_max_sharpe_under_null(n_trials, null_sharpe_dispersion(years)) / scale
    z = stats.norm.ppf(confidence)
    sr = sr_0
    for _ in range(64):
        denom = math.sqrt(max(1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr**2, 1e-12))
        nxt = sr_0 + z * denom / math.sqrt(n_obs - 1.0)
        if abs(nxt - sr) < 1e-15:
            break
        sr = nxt
    return sr * scale
