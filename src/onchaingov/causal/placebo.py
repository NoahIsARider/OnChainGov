"""Placebo tests for DID / PSM-DID estimates.

Two standard placebo checks:

1. **In-time placebo**: re-assign the treatment event to a pre-period date and
   re-estimate; the ATT should be statistically indistinguishable from zero.
2. **In-space placebo**: randomly permute the treatment group assignment and
   re-estimate; the distribution of pseudo-ATTs should center on zero.

Each test reports a test statistic (mean pseudo-ATT) and a share of
simulations with |pseudo-ATT| >= |true ATT| (an empirical p-value).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from onchaingov.causal.did import did_estimate


@dataclass
class PlaceboResult:
    """Output of a placebo test."""

    placebo_estimates: list[float]
    mean_placebo: float
    empirical_pvalue: float
    n_simulations: int
    test_type: str
    true_att: float | None = None

    def passed(self, alpha: float = 0.05) -> bool:
        """Placebo test passes if pseudo-ATTs are statistically null."""
        return self.empirical_pvalue > alpha


def _empirical_pvalue(pseudo: np.ndarray, true_att: float) -> float:
    if true_att == 0:
        return 1.0
    share = np.mean(np.abs(pseudo) >= abs(true_att))
    return float(share)


def in_time_placebo(
    df: pl.DataFrame,
    *,
    outcome: str,
    event_time: object,
    placebo_times: list[object],
    treatment: str = "treated",
    post: str = "post",
    unit_id: str = "unit_id",
    time_col: str = "period",
    covariates: list[str] | None = None,
) -> PlaceboResult:
    """Re-estimate the DID with the event moved to earlier placebo times.

    Args:
        event_time: The true treatment event time (used only for comparison).
        placebo_times: Candidate pre-period times to place the pseudo-event.
    """
    estimates: list[float] = []
    true_att: float | None = None
    for t in [event_time, *placebo_times]:
        df_ = df.with_columns((pl.col(time_col) >= t).cast(pl.Int8).alias(post))
        res = did_estimate(
            df_, outcome=outcome, treatment=treatment, post=post,
            unit_id=unit_id, time_col=time_col, covariates=covariates,
        )
        if true_att is None:
            true_att = res.att
        else:
            estimates.append(res.att)
    return PlaceboResult(
        placebo_estimates=estimates,
        mean_placebo=float(np.mean(estimates)),
        empirical_pvalue=_empirical_pvalue(np.asarray(estimates), true_att or 0.0),
        n_simulations=len(estimates),
        test_type="in_time",
        true_att=true_att,
    )


def in_space_placebo(
    df: pl.DataFrame,
    *,
    outcome: str,
    treatment: str = "treated",
    post: str = "post",
    unit_id: str = "unit_id",
    time_col: str = "period",
    covariates: list[str] | None = None,
    n_simulations: int = 100,
    seed: int | None = None,
) -> PlaceboResult:
    """Randomize treatment assignment and re-estimate the DID repeatedly.

    The empirical p-value is the fraction of simulations whose |pseudo-ATT|
    exceeds the |true ATT| from the actual assignment.
    """
    rng = np.random.default_rng(seed)
    units = df[unit_id].unique().to_list()
    treated_units = df.filter(pl.col(treatment) == 1)[unit_id].unique().to_list()
    true_res = did_estimate(
        df, outcome=outcome, treatment=treatment, post=post,
        unit_id=unit_id, time_col=time_col, covariates=covariates,
    )
    true_att = true_res.att
    n_treated = len(treated_units)

    estimates: list[float] = []
    for _ in range(n_simulations):
        permuted = set(rng.choice(units, size=n_treated, replace=False).tolist())
        df_ = df.with_columns(
            pl.col(unit_id).is_in(permuted).cast(pl.Int8).alias(treatment)
        )
        res = did_estimate(
            df_, outcome=outcome, treatment=treatment, post=post,
            unit_id=unit_id, time_col=time_col, covariates=covariates,
        )
        estimates.append(res.att)

    return PlaceboResult(
        placebo_estimates=estimates,
        mean_placebo=float(np.mean(estimates)),
        empirical_pvalue=_empirical_pvalue(np.asarray(estimates), true_att),
        n_simulations=n_simulations,
        test_type="in_space",
        true_att=true_att,
    )
