"""Feasibility analysis for the 60-75% annual return target (Phase 13).

This script answers three questions with arithmetic and simulation rather than
opinion:

  Q1. Given a strategy's true Sharpe ratio, what is the *maximum attainable*
      compound annual growth rate at any leverage, and what leverage achieves it?
  Q2. If we lever a strategy to hit a 60-75% CAGR, what drawdown distribution
      comes attached, under Gaussian, fat-tailed, and volatility-clustered
      return models?
  Q3. How much evidence would we need to distinguish a strategy with the
      required Sharpe from a worthless one, given the number of backtests we
      intend to run?

Nothing here is fitted to data. It is a property of compounding, of the
distribution of maximum drawdowns, and of the sampling distribution of the
Sharpe ratio. It therefore constrains what any strategy can deliver, including
ones we have not invented yet.

Usage:
    python research/analysis/return_target_feasibility.py > results/return_target_feasibility.md

Reproducibility: fixed seed (see SEED). No external data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

SEED = 20260826
DAYS_PER_YEAR = 365  # crypto trades 24/7/365
HORIZON_YEARS = 5
N_PATHS = 20_000

# Target band from the project brief.
TARGET_CAGR_LOW = 0.60
TARGET_CAGR_HIGH = 0.75


# ---------------------------------------------------------------------------
# Q1: the compounding ceiling
# ---------------------------------------------------------------------------
# For a strategy with arithmetic Sharpe S (excess of financing) run at
# annualised volatility sigma, the expected log growth rate is
#
#     g(sigma) = S * sigma - sigma^2 / 2
#
# This is maximised at sigma* = S (the full-Kelly volatility), giving
#
#     g_max = S^2 / 2   =>   CAGR_max = exp(S^2 / 2) - 1
#
# Leverage beyond sigma* *reduces* compound growth while still increasing
# drawdown. So exp(S^2/2) - 1 is a hard ceiling: no amount of leverage gets a
# strategy past it.


def max_cagr(sharpe: float) -> float:
    """Maximum attainable CAGR at any leverage, achieved at full Kelly."""
    return math.exp(sharpe**2 / 2.0) - 1.0


def cagr_at_kelly_fraction(sharpe: float, kelly_fraction: float) -> float:
    """Expected CAGR when running at `kelly_fraction` x full-Kelly volatility."""
    sigma = kelly_fraction * sharpe
    return math.exp(sharpe * sigma - sigma**2 / 2.0) - 1.0


def required_sharpe(target_cagr: float, kelly_fraction: float) -> float:
    """Sharpe needed to reach `target_cagr` while running at a given Kelly fraction.

    g = S*sigma - sigma^2/2 with sigma = k*S  =>  g = S^2 * (k - k^2/2)
    """
    g = math.log1p(target_cagr)
    coeff = kelly_fraction - kelly_fraction**2 / 2.0
    if coeff <= 0:
        return math.inf
    return math.sqrt(g / coeff)


# ---------------------------------------------------------------------------
# Q2: the drawdown that comes attached
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PathStats:
    median_cagr: float
    median_maxdd: float
    p95_maxdd: float
    prob_dd_over_30: float
    prob_dd_over_50: float
    prob_dd_over_70: float
    median_calmar: float


def _simulate_returns(
    rng: np.random.Generator,
    sharpe: float,
    ann_vol: float,
    n_days: int,
    n_paths: int,
    model: str,
) -> np.ndarray:
    """Daily *arithmetic* returns with the given annualised Sharpe and volatility.

    model:
      'gaussian' - iid normal. The optimistic case.
      'student_t' - iid Student-t(4), rescaled to the same volatility. Crypto
          daily returns have consistently shown tails at least this heavy.
      'garch' - Student-t(4) innovations through a GARCH(1,1) with crypto-like
          persistence (alpha=0.09, beta=0.90). Volatility clustering does not
          change the unconditional volatility but it *does* fatten the maximum
          drawdown distribution, because bad days arrive in runs.
    """
    daily_vol = ann_vol / math.sqrt(DAYS_PER_YEAR)
    daily_mu = sharpe * ann_vol / DAYS_PER_YEAR

    if model == "gaussian":
        z = rng.standard_normal((n_paths, n_days))
    elif model == "student_t":
        nu = 4.0
        z = rng.standard_t(nu, size=(n_paths, n_days)) / math.sqrt(nu / (nu - 2.0))
    elif model == "garch":
        nu = 4.0
        alpha, beta = 0.09, 0.90
        omega = 1.0 - alpha - beta  # unconditional variance of the z-process = 1
        eps = rng.standard_t(nu, size=(n_paths, n_days)) / math.sqrt(nu / (nu - 2.0))
        z = np.empty((n_paths, n_days))
        h = np.ones(n_paths)
        for t in range(n_days):
            shock = np.sqrt(h) * eps[:, t]
            z[:, t] = shock
            h = omega + alpha * shock**2 + beta * h
    else:
        raise ValueError(f"unknown model {model!r}")

    return daily_mu + daily_vol * z


def _path_stats(returns: np.ndarray, years: float) -> PathStats:
    """Drawdown and growth statistics from arithmetic daily returns."""
    # Cap at -100%: a levered path can print a return below -1 in the raw model.
    # In reality that is a wipeout, so we floor equity at zero rather than
    # letting it go negative and produce nonsense compounding.
    growth = np.maximum(1.0 + returns, 1e-12)
    equity = np.cumprod(growth, axis=1)
    peak = np.maximum.accumulate(equity, axis=1)
    dd = 1.0 - equity / peak
    maxdd = dd.max(axis=1)

    final = equity[:, -1]
    cagr = np.power(np.maximum(final, 1e-12), 1.0 / years) - 1.0

    with np.errstate(divide="ignore", invalid="ignore"):
        calmar = np.where(maxdd > 1e-9, cagr / maxdd, np.nan)

    return PathStats(
        median_cagr=float(np.median(cagr)),
        median_maxdd=float(np.median(maxdd)),
        p95_maxdd=float(np.percentile(maxdd, 95)),
        prob_dd_over_30=float((maxdd > 0.30).mean()),
        prob_dd_over_50=float((maxdd > 0.50).mean()),
        prob_dd_over_70=float((maxdd > 0.70).mean()),
        median_calmar=float(np.nanmedian(calmar)),
    )


def simulate(sharpe: float, ann_vol: float, model: str, rng: np.random.Generator) -> PathStats:
    n_days = int(HORIZON_YEARS * DAYS_PER_YEAR)
    returns = _simulate_returns(rng, sharpe, ann_vol, n_days, N_PATHS, model)
    return _path_stats(returns, HORIZON_YEARS)


# ---------------------------------------------------------------------------
# Q3: can we even measure the Sharpe we would need?
# ---------------------------------------------------------------------------


def sharpe_standard_error(sharpe: float, years: float, obs_per_year: int = DAYS_PER_YEAR) -> float:
    """Lo (2002) asymptotic SE of an annualised Sharpe estimate, iid case.

    SE(S_hat) ~ sqrt((1 + S^2/2) / T) with T in years. Serial correlation and
    negative skew make the true SE larger, so this is a *lower bound* on our
    uncertainty.
    """
    del obs_per_year
    return math.sqrt((1.0 + sharpe**2 / 2.0) / years)


def expected_max_sharpe_under_null(n_trials: int, se: float) -> float:
    """Expected best in-sample Sharpe from `n_trials` worthless strategies.

    Bailey & Lopez de Prado's expected-maximum-Sharpe approximation for N
    independent trials each drawn from N(0, se^2):

        E[max] ~ se * ((1-g) * z(1 - 1/N) + g * z(1 - 1/(N*e)))

    with g the Euler-Mascheroni constant. This is the number an *edgeless*
    search is expected to produce. Any in-sample Sharpe below it is evidence
    of nothing at all.
    """
    if n_trials < 2:
        return 0.0
    g = 0.5772156649015329
    z1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return se * ((1.0 - g) * z1 + g * z2)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def main() -> None:
    rng = np.random.default_rng(SEED)

    print("# Return-Target Feasibility Analysis")
    print()
    print("*Generated by `research/analysis/return_target_feasibility.py`. "
          f"Seed {SEED}, {N_PATHS:,} paths, {HORIZON_YEARS}-year horizon, "
          f"{DAYS_PER_YEAR} trading days/year.*")
    print()
    print("This file is generated. Do not edit by hand; re-run the script.")
    print()
    print("---")
    print()

    # -- Q1 ------------------------------------------------------------------
    print("## 1. The compounding ceiling")
    print()
    print("For a strategy with true Sharpe `S` run at annualised volatility `sigma`,")
    print("expected log growth is `g = S*sigma - sigma^2/2`, maximised at `sigma = S`.")
    print("So the **maximum CAGR attainable at any leverage** is `exp(S^2/2) - 1`.")
    print("Leverage past that point lowers compound growth while still raising drawdown.")
    print()
    print("| True Sharpe | Max CAGR (full Kelly) | Vol at full Kelly | CAGR at 1/2 Kelly | CAGR at 1/4 Kelly |")
    print("|---|---|---|---|---|")
    for s in [0.3, 0.5, 0.7, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5]:
        print(
            f"| {s:.1f} | {_pct(max_cagr(s))} | {_pct(s)} | "
            f"{_pct(cagr_at_kelly_fraction(s, 0.5))} | {_pct(cagr_at_kelly_fraction(s, 0.25))} |"
        )
    print()
    print("**Sharpe required to reach the target band:**")
    print()
    print("| Target CAGR | Full Kelly | 1/2 Kelly | 1/4 Kelly |")
    print("|---|---|---|---|")
    for target in [TARGET_CAGR_LOW, 0.65, TARGET_CAGR_HIGH, 1.00]:
        row = " | ".join(
            f"{required_sharpe(target, k):.2f}" for k in (1.0, 0.5, 0.25)
        )
        print(f"| {_pct(target)} | {row} |")
    print()

    # -- Q2 ------------------------------------------------------------------
    print("## 2. The drawdown attached to the target")
    print()
    print("Each row is levered to the volatility that produces roughly the target CAGR")
    print("for that Sharpe. `student_t` uses Student-t(4) innovations; `garch` adds")
    print("GARCH(1,1) volatility clustering (alpha=0.09, beta=0.90) on top.")
    print()

    scenarios = []
    for s in [0.7, 1.0, 1.2, 1.5, 2.0]:
        # Solve S*sigma - sigma^2/2 = ln(1+target) for the smaller root
        # (the lower-leverage solution), when one exists.
        g = math.log1p(0.65)
        disc = s**2 - 2 * g
        if disc < 0:
            continue  # 65% CAGR unreachable at this Sharpe, at any leverage
        sigma = s - math.sqrt(disc)
        scenarios.append((s, sigma))

    for model in ("gaussian", "student_t", "garch"):
        print(f"### Return model: `{model}`")
        print()
        print("| Sharpe | Ann. vol needed | Median CAGR | Median MaxDD | 95th-pct MaxDD | P(DD>30%) | P(DD>50%) | P(DD>70%) | Median Calmar |")
        print("|---|---|---|---|---|---|---|---|---|")
        for s, sigma in scenarios:
            st = simulate(s, sigma, model, rng)
            print(
                f"| {s:.1f} | {_pct(sigma)} | {_pct(st.median_cagr)} | {_pct(st.median_maxdd)} | "
                f"{_pct(st.p95_maxdd)} | {_pct(st.prob_dd_over_30)} | {_pct(st.prob_dd_over_50)} | "
                f"{_pct(st.prob_dd_over_70)} | {st.median_calmar:.2f} |"
            )
        print()

    print("Sharpe values omitted from the table cannot reach 65% CAGR at *any* leverage.")
    print()

    # -- Q3 ------------------------------------------------------------------
    print("## 3. Could we even detect the required Sharpe?")
    print()
    print("Standard error of an annualised Sharpe estimate, by sample length")
    print("(iid assumption -- the true SE is larger under autocorrelation and negative skew):")
    print()
    print("| True Sharpe | 2y SE | 3y SE | 5y SE | 8y SE | 95% CI on a 5y estimate |")
    print("|---|---|---|---|---|---|")
    for s in [0.5, 1.0, 1.2, 1.5, 2.0]:
        ses = [sharpe_standard_error(s, y) for y in (2, 3, 5, 8)]
        lo, hi = s - 1.96 * ses[2], s + 1.96 * ses[2]
        print(
            f"| {s:.1f} | {ses[0]:.2f} | {ses[1]:.2f} | {ses[2]:.2f} | {ses[3]:.2f} | "
            f"[{lo:.2f}, {hi:.2f}] |"
        )
    print()
    print("**Expected best in-sample Sharpe from a search over worthless strategies.**")
    print("This is what a search with *zero* real edge is expected to hand us, purely")
    print("from selecting the maximum of N noisy estimates. Any backtest Sharpe below")
    print("the relevant cell is evidence of nothing.")
    print()
    header_years = (2, 3, 5, 8)
    print("| Trials | " + " | ".join(f"{y}y sample" for y in header_years) + " |")
    print("|---|" + "---|" * len(header_years))
    for n in (10, 50, 100, 500, 1_000, 10_000):
        cells = []
        for y in header_years:
            se = sharpe_standard_error(0.0, y)
            cells.append(f"{expected_max_sharpe_under_null(n, se):.2f}")
        print(f"| {n:,} | " + " | ".join(cells) + " |")
    print()
    print("A parameter sweep over 6 parameters at 5 values each is 15,625 trials.")
    print("Read the table before running one.")
    print()


if __name__ == "__main__":
    main()
