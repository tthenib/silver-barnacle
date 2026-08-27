"""Power analysis of the research protocol itself (not of any strategy).

BACKTESTING_PROTOCOL.md specifies a multi-stage gauntlet: select on a development
sample, then require a validation result, walk-forward consistency, cross-asset
consistency, and a Deflated-Sharpe-corrected out-of-sample result. Every gate is
individually sensible. Nobody usually asks the two questions that decide whether
the whole thing is worth running:

  Q1. If a genuine edge exists among the things we try, what is the probability
      our process actually finds and ships it?          (statistical POWER)

  Q2. If no genuine edge exists at all, what is the probability our process
      ships something anyway?                     (FALSE DEPLOYMENT rate)

And the one that matters most in practice:

  Q3. Given both, if the protocol says "ship it", what is the probability the
      thing actually works?          (POSITIVE PREDICTIVE VALUE)

The counterintuitive result this produces -- that power *collapses* as the number
of strategies tried increases, because the search starts preferring lucky null
strategies over genuinely-edged ones -- is the single most actionable finding
available to us before any data is collected. It converts "count your trials"
into "budget your trials, and here is the budget."

Method: needle-in-a-haystack Monte Carlo. A search over N candidates contains
either N worthless strategies, or N-1 worthless ones plus a single genuinely
edged "needle". Each candidate is scored on the development sample; the best is
selected; the winner is then put through the protocol's gates. Sharpe estimates
are drawn from their asymptotic sampling distribution (Lo 2002) rather than by
simulating daily returns -- exact for the maximum-of-N step, and fast enough to
run the whole grid in seconds.

Usage:
    python research/analysis/research_power.py > results/research_power.md

Reproducibility: fixed seed. No external data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats

from _stats import deflated_sharpe_threshold, sharpe_standard_error

SEED = 20260827
N_SIMS = 200_000

# --- Protocol geometry, mirroring BACKTESTING_PROTOCOL.md sec.2.2 ------------
DEV_YEARS = 5.0            # 2017-2021, free exploration, where selection happens
VAL_YEARS = 2.0            # 2022-2023, model selection
TEST_YEARS = 2.7           # 2024-present, opened once
OOS_YEARS = VAL_YEARS + TEST_YEARS

# --- Gate thresholds, mirroring STRATEGY_HYPOTHESES.md sec.5.3 ---------------
GATE_DEV_MIN_SHARPE = 0.30      # a candidate must at least look plausible
GATE_VAL_MIN_SHARPE = 0.40      # proxy for "beats vol-targeted buy & hold (B2)"
WF_WINDOWS = 8                  # 8 x 6-month walk-forward windows
WF_MIN_POSITIVE = 5             # >= 5 of 8 windows positive
XASSET_COUNT = 5                # BTC + 4 others
XASSET_MIN_POSITIVE = 4         # >= 4 of 5 same-sign
XASSET_CORRELATION = 0.80       # crypto assets are NOT independent tests
DSR_CONFIDENCE = 0.95


@dataclass(frozen=True)
class Outcome:
    p_needle_selected: float      # search picked the genuinely-edged candidate
    p_deploy_needle: float        # ...and it cleared every gate
    p_deploy_null: float          # a worthless candidate cleared every gate
    p_deploy_any: float


def _max_of_n_normals(rng: np.random.Generator, n: int, scale: float, size: int) -> np.ndarray:
    """Exact sample of max(N iid N(0, scale^2)) via the inverse CDF of the maximum.

    P(max <= x) = Phi(x/scale)^N, so max = scale * Phi^-1(U^(1/N)) with U uniform.
    This avoids materialising N candidates per simulation.
    """
    if n <= 0:
        return np.full(size, -np.inf)
    u = rng.random(size)
    return scale * stats.norm.ppf(np.power(u, 1.0 / n))


def _run_gates(
    rng: np.random.Generator,
    true_sharpe: np.ndarray,
    winner_dev_sharpe: np.ndarray,
    n_trials: int,
    size: int,
) -> np.ndarray:
    """Apply protocol gates to selected winners. Returns a boolean pass mask.

    Gate order mirrors BACKTESTING_PROTOCOL.md sec.5.1. The Deflated Sharpe gate
    is applied to the DEVELOPMENT sample, where selection actually happened --
    that is the estimate selection bias contaminates. The out-of-sample record
    then faces a plain benchmark test, not a second deflation.
    """
    se_val = sharpe_standard_error(0.0, VAL_YEARS) * np.sqrt(1.0 + true_sharpe**2 / 2.0)
    se_test = sharpe_standard_error(0.0, TEST_YEARS) * np.sqrt(1.0 + true_sharpe**2 / 2.0)

    # Deflated Sharpe on the selection sample: the trial-count penalty.
    gate_dsr = winner_dev_sharpe > deflated_sharpe_threshold(
        n_trials, DEV_YEARS, DSR_CONFIDENCE
    )

    # Cross-asset estimates, correlated. Asset 0 IS the primary symbol, so its
    # validation estimate is also the validation gate's input -- one asset
    # cannot have two different validation results.
    z_common = rng.standard_normal(size)
    z_idio = rng.standard_normal((XASSET_COUNT, size))
    rho = XASSET_CORRELATION
    z = math.sqrt(rho) * z_common + math.sqrt(1.0 - rho) * z_idio
    xasset_sharpe = true_sharpe + se_val * z

    val_sharpe = xasset_sharpe[0]
    gate_val = val_sharpe > GATE_VAL_MIN_SHARPE
    gate_xasset = (xasset_sharpe > 0.0).sum(axis=0) >= XASSET_MIN_POSITIVE

    # Walk-forward window signs. P(window positive) = Phi(S * sqrt(window years)).
    p_pos = stats.norm.cdf(true_sharpe * math.sqrt(0.5))
    gate_wf = rng.binomial(WF_WINDOWS, p_pos) >= WF_MIN_POSITIVE

    # Final out-of-sample record must still beat the benchmark.
    test_sharpe = true_sharpe + se_test * rng.standard_normal(size)
    pooled = (VAL_YEARS * val_sharpe + TEST_YEARS * test_sharpe) / OOS_YEARS
    gate_oos = pooled > GATE_VAL_MIN_SHARPE

    return gate_dsr & gate_val & gate_wf & gate_xasset & gate_oos


def simulate(n_trials: int, edge_sharpe: float, rng: np.random.Generator, size: int = N_SIMS) -> Outcome:
    """One search of `n_trials` candidates: n_trials-1 nulls plus one needle."""
    se_null_dev = sharpe_standard_error(0.0, DEV_YEARS)
    se_edge_dev = sharpe_standard_error(edge_sharpe, DEV_YEARS)

    best_null_dev = _max_of_n_normals(rng, n_trials - 1, se_null_dev, size)
    needle_dev = edge_sharpe + se_edge_dev * rng.standard_normal(size)

    needle_wins = needle_dev > best_null_dev
    winner_dev = np.where(needle_wins, needle_dev, best_null_dev)
    winner_true = np.where(needle_wins, edge_sharpe, 0.0)

    gate_dev = winner_dev > GATE_DEV_MIN_SHARPE
    passed = gate_dev & _run_gates(rng, winner_true, winner_dev, n_trials, size)

    return Outcome(
        p_needle_selected=float(needle_wins.mean()),
        p_deploy_needle=float((passed & needle_wins).mean()),
        p_deploy_null=float((passed & ~needle_wins).mean()),
        p_deploy_any=float(passed.mean()),
    )


def simulate_no_edge(n_trials: int, rng: np.random.Generator, size: int = N_SIMS) -> float:
    """False deployment rate when every candidate is worthless."""
    se_null_dev = sharpe_standard_error(0.0, DEV_YEARS)
    best_dev = _max_of_n_normals(rng, n_trials, se_null_dev, size)
    gate_dev = best_dev > GATE_DEV_MIN_SHARPE
    passed = gate_dev & _run_gates(rng, np.zeros(size), best_dev, n_trials, size)
    return float(passed.mean())


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def main() -> None:
    rng = np.random.default_rng(SEED)

    print("# Power Analysis of the Research Protocol")
    print()
    print(f"*Generated by `research/analysis/research_power.py`. Seed {SEED}, "
          f"{N_SIMS:,} simulations per cell.*")
    print()
    print("This file is generated. Do not edit by hand; re-run the script.")
    print()
    print("This analyses **our process**, not any strategy. It asks what the protocol in")
    print("`BACKTESTING_PROTOCOL.md` would do if a real edge existed, and what it would do")
    print("if none did. No market data is involved.")
    print()
    print("---")
    print()

    trial_grid = [1, 5, 10, 25, 50, 100, 250, 500, 1_000, 5_000]

    # ---------------------------------------------------------------- Q1 ----
    print("## 1. Does the search even select the real edge?")
    print()
    print("A search over N candidates containing one genuinely-edged strategy and N-1")
    print("worthless ones. The winner is whichever scores best on the 5-year development")
    print("sample. Probability the winner is the *real* one:")
    print()
    print("| Trials | needle Sharpe 0.4 | 0.6 | 0.8 | 1.0 |")
    print("|---|---|---|---|---|")
    for n in trial_grid:
        cells = [_pct(simulate(n, s, rng).p_needle_selected) for s in (0.4, 0.6, 0.8, 1.0)]
        print(f"| {n:,} | " + " | ".join(cells) + " |")
    print()
    print("**A larger search is a worse search.** Every additional worthless candidate is")
    print("another lottery ticket for noise, and noise has a 5-year standard error of 0.45")
    print("while a real Sharpe-0.6 edge only has a mean of 0.6. Past a few hundred trials")
    print("the search is, in effect, selecting the luckiest null strategy almost every time.")
    print()

    # ---------------------------------------------------------------- Q2 ----
    print("## 2. End-to-end power and false deployment")
    print()
    print("`Power` = P(the real edge is selected **and** clears every gate).")
    print("`False deploy` = P(a worthless strategy clears every gate), searches with no edge present.")
    print()
    print("| Trials | Power @ S=0.4 | @ S=0.6 | @ S=0.8 | @ S=1.0 | False deploy |")
    print("|---|---|---|---|---|---|")
    fp_by_n: dict[int, float] = {}
    power_by_n: dict[int, dict[float, float]] = {}
    for n in trial_grid:
        row = {}
        for s in (0.4, 0.6, 0.8, 1.0):
            row[s] = simulate(n, s, rng).p_deploy_needle
        power_by_n[n] = row
        fp = simulate_no_edge(n, rng)
        fp_by_n[n] = fp
        cells = " | ".join(_pct(row[s]) for s in (0.4, 0.6, 0.8, 1.0))
        print(f"| {n:,} | {cells} | {_pct(fp)} |")
    print()
    print("The false-deployment rate stays low because the Deflated Sharpe gate widens as")
    print("trials increase -- that gate is doing its job. But it defends by raising the bar")
    print("for *everything*, so it suppresses real edges at the same time. The protocol")
    print("does not distinguish 'lucky' from 'good'; it only distinguishes 'extreme' from")
    print("'not extreme'.")
    print()

    # ---------------------------------------------------------------- Q3 ----
    print("## 3. If the protocol says ship it, is it real?")
    print()
    print("Positive predictive value, for a prior probability `p` that a real edge exists")
    print("among the candidates at all. Given how many people have looked for tradeable")
    print("crypto trend edges, a prior above ~20% is generous.")
    print()
    ppv_sims = 1_000_000
    print("| Trials | PPV @ p=5% | @ p=20% | @ p=50% |")
    print("|---|---|---|---|")
    for n in trial_grid:
        out = simulate(n, 0.6, rng, size=ppv_sims)
        fp = simulate_no_edge(n, rng, size=ppv_sims)
        n_events = (out.p_deploy_any + fp) * ppv_sims
        cells = []
        for p in (0.05, 0.20, 0.50):
            num = p * out.p_deploy_needle
            den = p * (out.p_deploy_needle + out.p_deploy_null) + (1 - p) * fp
            cells.append(_pct(num / den) if den > 0 else "n/a")
        flag = " †" if n_events < 200 else ""
        print(f"| {n:,} | " + " | ".join(cells) + f"{flag} |")
    print()
    print(f"† fewer than 200 simulated deployments in {ppv_sims:,} runs -- Monte Carlo noise")
    print("dominates these cells; read them as \"small\", not as the printed digits.")
    print()
    print("PPV stays high across the grid, but for a reason that is not comfort: the")
    print("protocol almost never ships **anything**. Conditional on shipping, we are")
    print("probably right. Unconditionally, we are probably empty-handed -- see section 2.")
    print()

    # ------------------------------------------------------------- budget ----
    print("## 4. The affordable trial budget")
    print()
    print("Largest trial count retaining a given end-to-end power, by the size of the edge")
    print("we are hoping to find. `max power` is what a **single pre-specified** candidate")
    print("achieves -- the ceiling, before any search cost at all.")
    print()
    fine_grid = [1, 2, 3, 5, 8, 12, 20, 30, 50, 75, 100, 150, 250, 400, 600, 1_000]
    print("| True Sharpe | max power (N=1) | N for 20% power | for 10% | for 5% |")
    print("|---|---|---|---|---|")
    for s in (0.4, 0.6, 0.8, 1.0, 1.3):
        powers = {n: simulate(n, s, rng, size=250_000).p_deploy_needle for n in fine_grid}
        cells = []
        for target in (0.20, 0.10, 0.05):
            affordable = [n for n in fine_grid if powers[n] >= target]
            cells.append(str(max(affordable)) if affordable else "**none**")
        print(f"| {s:.1f} | {_pct(powers[1])} | " + " | ".join(cells) + " |")
    print()
    print("**This is the finding that should change how we work.** Two things follow:")
    print()
    print("1. Against the edge size we actually expect (Sharpe 0.4-0.7,")
    print("   `STRATEGY_HYPOTHESES.md` sec.5.4), the protocol as written is close to")
    print("   unable to approve anything, *even with no search at all*. It is not")
    print("   calibrated for the effect size we are hunting.")
    print("2. Trials are a shared, exhaustible budget. A single 6-parameter sweep")
    print("   (15,625 trials) does not merely waste power -- it removes essentially all")
    print("   of it, permanently, for every hypothesis that follows on the same data.")
    print()

    # ------------------------------------------------------------ gate cost --
    print("## 5. Which gate does the damage?")
    print()
    print("Marginal pass rate of each gate against a strategy with a **genuine** Sharpe of")
    print("0.6, ignoring the selection step. A gate that rejects most real edges is buying")
    print("its safety expensively. Deflation thresholds shown at 10 and 100 trials.")
    print()
    size = 200_000
    s = 0.6
    true_sharpe = np.full(size, s)
    se_dev = sharpe_standard_error(s, DEV_YEARS)
    se_val = sharpe_standard_error(s, VAL_YEARS)
    se_test = sharpe_standard_error(s, TEST_YEARS)
    dev = true_sharpe + se_dev * rng.standard_normal(size)
    z_common = rng.standard_normal(size)
    z_idio = rng.standard_normal((XASSET_COUNT, size))
    z = math.sqrt(XASSET_CORRELATION) * z_common + math.sqrt(1 - XASSET_CORRELATION) * z_idio
    xa = true_sharpe + se_val * z
    val = xa[0]
    test = true_sharpe + se_test * rng.standard_normal(size)
    pooled = (VAL_YEARS * val + TEST_YEARS * test) / OOS_YEARS
    thr10 = deflated_sharpe_threshold(10, DEV_YEARS, DSR_CONFIDENCE)
    thr100 = deflated_sharpe_threshold(100, DEV_YEARS, DSR_CONFIDENCE)

    gates = {
        f"Dev plausibility screen (SR > {GATE_DEV_MIN_SHARPE})": dev > GATE_DEV_MIN_SHARPE,
        f"Deflated Sharpe @ 10 trials (dev SR > {thr10:.2f})": dev > thr10,
        f"Deflated Sharpe @ 100 trials (dev SR > {thr100:.2f})": dev > thr100,
        f"Validation Sharpe > {GATE_VAL_MIN_SHARPE}": val > GATE_VAL_MIN_SHARPE,
        f"Walk-forward >= {WF_MIN_POSITIVE}/{WF_WINDOWS} windows positive":
            rng.binomial(WF_WINDOWS, stats.norm.cdf(s * math.sqrt(0.5)), size) >= WF_MIN_POSITIVE,
        f"Cross-asset >= {XASSET_MIN_POSITIVE}/{XASSET_COUNT} same sign":
            (xa > 0).sum(axis=0) >= XASSET_MIN_POSITIVE,
        f"Pooled OOS Sharpe > {GATE_VAL_MIN_SHARPE}": pooled > GATE_VAL_MIN_SHARPE,
    }
    print("| Gate | Passes a real S=0.6 edge |")
    print("|---|---|")
    for name, mask in gates.items():
        print(f"| {name} | {_pct(float(mask.mean()))} |")
    combined = np.ones(size, dtype=bool)
    for name, mask in gates.items():
        if "@ 100 trials" in name:
            continue  # count the 10-trial deflation only, to avoid double-applying
        combined &= mask
    print(f"| **All gates combined (10-trial deflation)** | **{_pct(float(combined.mean()))}** |")
    print()
    print("The Deflated Sharpe gate is the binding constraint, and it is the one whose")
    print("severity we control directly -- through the trial count we choose to spend.")
    print("Note it tightens from 1.44 to 1.87 purely by going from 10 trials to 100:")
    print("that gap is the price of a sweep, paid by every real edge we might have had.")
    print()


if __name__ == "__main__":
    main()
