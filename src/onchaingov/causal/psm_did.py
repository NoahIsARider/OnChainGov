"""Propensity Score Matching + Difference-in-Differences (PSM-DID).

Pipeline:
1. Estimate a propensity score logit for treatment assignment from baseline
   covariates.
2. Match treated units to control units via nearest-neighbor matching on the
   logit (or the score).
3. Re-weight the matched control group and run the DID estimator on the
   matched sample with sampling weights.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from onchaingov.causal.did import DIDResult, did_estimate


@dataclass
class MatchResult:
    """Result of PSM matching."""

    matched_df: pl.DataFrame
    propensity_scores: pl.DataFrame
    matched_pairs: list[tuple[str, str]] | None = None
    caliper: float | None = None

    @property
    def matched_n(self) -> int:
        return self.matched_df.height

    @property
    def control_n(self) -> int:
        if "weight" not in self.matched_df.columns:
            return 0
        return int((self.matched_df["weight"] > 0).sum())


def propensity_scores(
    df: pl.DataFrame,
    *,
    treatment: str = "treated",
    unit_id: str = "unit_id",
    covariates: list[str] | None = None,
    max_iter: int = 100,
) -> tuple[pl.DataFrame, np.ndarray]:
    """Estimate propensity scores via logistic regression.

    Returns a tuple of (unit frame with ``pscore`` column, score array aligned
    with input row order).

    The unit-level covariates are aggregated to one row per unit (mean over
    periods). Raises ``ValueError`` if a covariate is missing.
    """
    covs = covariates or [c for c in df.columns if c.startswith("covariate_")]
    if not covs:
        raise ValueError("no covariates provided for propensity score estimation")
    missing = set(covs) - set(df.columns)
    if missing:
        raise ValueError(f"covariates not in panel: {sorted(missing)}")

    try:
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:  # pragma: no cover
        raise ImportError("scikit-learn is required for PSM") from exc

    unit = (
        df.group_by([unit_id, treatment])
        .agg([pl.col(c).mean().alias(c) for c in covs])
    )
    X = unit.select(covs).to_numpy().astype(np.float64)
    y = unit[treatment].to_numpy().astype(np.int64)

    # drop any units with NaN in covariates (no baseline data)
    valid = ~np.isnan(X).any(axis=1)
    X_v, y_v = X[valid], y[valid]
    if len(np.unique(y_v)) < 2:
        raise ValueError("treatment indicator has no variation in the unit sample")

    model = LogisticRegression(max_iter=max_iter, solver="lbfgs")
    model.fit(X_v, y_v)
    pscore = model.predict_proba(X_v)[:, 1]

    out = unit.filter(pl.Series(valid)).with_columns(pl.Series("pscore", pscore))
    return out, pscore


def match_units(
    unit_df: pl.DataFrame,
    *,
    treatment: str = "treated",
    unit_id: str = "unit_id",
    caliper: float = 0.05,
    replace: bool = True,
) -> list[tuple[str, str]]:
    """Nearest-neighbor matching on propensity score.

    For each treated unit, finds the control unit with the closest score
    within the caliper. Returns a list of (treated_id, control_id) pairs.

    Args:
        unit_df: Unit-level frame with ``pscore`` column and treatment indicator.
        caliper: Maximum allowed |pscore_t - pscore_c| distance.
        replace: Allow control units to be reused.

    Raises:
        ValueError: if either group is empty.
    """
    treated_df = unit_df.filter(pl.col(treatment) == 1)
    control_df = unit_df.filter(pl.col(treatment) == 0)
    if treated_df.height == 0 or control_df.height == 0:
        raise ValueError("both treated and control units are required for matching")

    treated_scores = treated_df["pscore"].to_numpy().astype(np.float64)
    control_scores = control_df["pscore"].to_numpy().astype(np.float64)
    control_ids = control_df[unit_id].to_list()

    pairs: list[tuple[str, str]] = []
    used = np.zeros(len(control_scores), dtype=bool)
    for i, ts in enumerate(treated_scores):
        dists = np.abs(control_scores - ts)
        if not replace:
            dists = np.where(used, np.inf, dists)
        j = int(np.argmin(dists))
        if dists[j] <= caliper:
            pairs.append((treated_df[unit_id][i], control_ids[j]))
            used[j] = True
    return pairs


def psm_did_estimate(
    df: pl.DataFrame,
    *,
    outcome: str,
    treatment: str = "treated",
    post: str = "post",
    unit_id: str = "unit_id",
    time_col: str = "period",
    covariates: list[str] | None = None,
    caliper: float = 0.05,
    replace: bool = True,
    use_weighted_did: bool = False,
) -> tuple[DIDResult, MatchResult]:
    """Run PSM-DID estimation.

    Matches treated and control units on baseline covariates, then estimates
    the DID on the matched sample. Optionally weights the DID regression by
    matching weights (frequency of each control's use).

    Returns a (DIDResult, MatchResult) tuple.
    """
    unit_df, _ = propensity_scores(df, treatment=treatment, unit_id=unit_id, covariates=covariates)
    pairs = match_units(unit_df, treatment=treatment, unit_id=unit_id, caliper=caliper, replace=replace)
    if not pairs:
        raise ValueError("no matches found within the caliper; try a larger caliper")

    matched_ids = set()
    for t_id, c_id in pairs:
        matched_ids.add(t_id)
        matched_ids.add(c_id)

    matched = df.filter(pl.col(unit_id).is_in(matched_ids))

    if use_weighted_did:
        control_use = {}
        for _, c_id in pairs:
            control_use[c_id] = control_use.get(c_id, 0) + 1
        matched = matched.with_columns(
            pl.col(unit_id)
            .map_elements(lambda u: float(control_use.get(u, 1.0)), return_dtype=pl.Float64)
            .alias("weight")
        )
        result = did_estimate(
            matched, outcome=outcome, treatment=treatment, post=post,
            unit_id=unit_id, time_col=time_col, covariates=covariates,
        )
        result.details["weights_applied"] = True
    else:
        result = did_estimate(
            matched, outcome=outcome, treatment=treatment, post=post,
            unit_id=unit_id, time_col=time_col, covariates=covariates,
        )
        matched = matched.with_columns(pl.lit(1.0).alias("weight"))

    match_result = MatchResult(
        matched_df=matched,
        propensity_scores=unit_df,
        matched_pairs=pairs,
        caliper=caliper,
    )
    result.model_type = "psm_did"
    return result, match_result
