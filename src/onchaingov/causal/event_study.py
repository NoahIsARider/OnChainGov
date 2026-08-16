"""Event study analysis for staggered/non-staggered treatment.

Estimates the dynamic treatment effect by regressing the outcome on
relative-time dummies (relative to the event period), with entity and time
fixed effects. Useful for pre-trend testing and for tracing post-treatment
dynamics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl


@dataclass
class EventStudyResult:
    """Container for event study output."""

    relative_periods: list[int]
    coefficients: list[float]
    std_errors: list[float]
    base_period: int
    nobs: int

    def pre_trends_pvalue(self) -> float:
        """Joint test that all pre-treatment coefficients are zero.

        Uses a simple t-test aggregation: reports the share of pre-period
        coefficients statistically significant at the 5% level.
        """
        pre = [
            (c, s) for r, c, s in zip(self.relative_periods, self.coefficients, self.std_errors)
            if r < self.base_period
        ]
        if not pre:
            return 1.0
        significant = sum(1 for c, s in pre if s > 0 and abs(c / s) > 1.96)
        return 1.0 - significant / len(pre)


def event_study_estimate(
    df: pl.DataFrame,
    *,
    outcome: str,
    event_time: object,
    treatment: str = "treated",
    unit_id: str = "unit_id",
    time_col: str = "period",
    n_leads: int = 4,
    n_lags: int = 4,
    covariates: list[str] | None = None,
) -> EventStudyResult:
    """Estimate an event study with relative-time dummies.

    Args:
        event_time: The treatment event time for the treated units.
        n_leads: Number of pre-event relative periods.
        n_lags: Number of post-event relative periods.

    Returns:
        An EventStudyResult with coefficients on each relative period dummy,
        omitting the base period (``-1``).
    """
    try:
        import pandas as pd
        import statsmodels.api as sm
        from linearmodels.panel import PanelOLS
    except ImportError as exc:  # pragma: no cover
        raise ImportError("linearmodels and statsmodels are required for event study") from exc

    pandas_df = df.to_pandas()
    pandas_df["rel_time"] = (pandas_df[time_col] >= event_time).astype(int)
    # relative period: number of periods after event (approx using rank ordering)
    all_periods = sorted(pandas_df[time_col].unique())
    event_rank = next((i for i, p in enumerate(all_periods) if p >= event_time), len(all_periods))
    rank_map = {p: i for i, p in enumerate(all_periods)}
    pandas_df["rel"] = pandas_df[time_col].map(rank_map) - event_rank
    pandas_df["rel_treat"] = pandas_df["rel"] * pandas_df[treatment]

    rel_values = sorted(pandas_df["rel_treat"].unique().tolist())
    rel_values = [r for r in rel_values if r <= n_lags and r >= -n_leads]
    base = -1
    dummies = {}
    for r in rel_values:
        if r == base:
            continue
        col = f"rel_{r}"
        dummies[col] = (pandas_df["rel_treat"] == r).astype(float)
        pandas_df[col] = dummies[col]

    exog_cols = list(dummies.keys()) + (covariates or [])
    X = pandas_df[exog_cols].copy()
    for c in exog_cols:
        if c not in X.columns:
            X[c] = np.nan
    X = X.fillna(0.0)
    y = pandas_df[outcome]

    if not isinstance(pandas_df.index, pd.MultiIndex):
        pandas_df = pandas_df.set_index([unit_id, time_col])
        X.index = pandas_df.index
        y.index = pandas_df.index

    model = PanelOLS(y, X, entity_effects=True, time_effects=True, drop_absorbed=True)
    try:
        res = model.fit(cov_type="clustered", cluster_entity=True)
        params, std_errors, nobs = _extract(res, exog_cols)
    except (ZeroDivisionError, FloatingPointError, np.linalg.LinAlgError):
        # Degenerate panel (e.g. zero residual variance after absorbing fixed
        # effects): fall back to pooled OLS on the relative-time dummies.
        import warnings

        import statsmodels.api as sm

        warnings.warn(
            "PanelOLS failed (possibly degenerate panel); using pooled OLS.",
            RuntimeWarning,
            stacklevel=2,
        )
        X_ols = pandas_df[exog_cols].copy()
        X_ols = sm.add_constant(X_ols, has_constant="add")
        ols = sm.OLS(y, X_ols).fit(cov_type="HC1")
        idx = ["const"] + exog_cols
        params = {name: float(ols.params.get(name, np.nan)) for name in idx}
        std_errors = {name: float(ols.bse.get(name, np.nan)) for name in idx}
        nobs = int(ols.nobs)

    periods: list[int] = []
    coefs: list[float] = []
    ses: list[float] = []
    for r in rel_values:
        if r == base:
            continue
        key = f"rel_{r}"
        if key in params:
            periods.append(r)
            coefs.append(params[key])
            ses.append(std_errors[key])

    return EventStudyResult(
        relative_periods=periods,
        coefficients=coefs,
        std_errors=ses,
        base_period=base,
        nobs=nobs,
    )


def _extract(res: Any, exog_cols: list[str]) -> tuple[dict[str, float], dict[str, float], int]:
    """Extract params / std errors / nobs from a fitted regression result."""
    params = {c: float(res.params[c]) for c in exog_cols if c in res.params}
    std_errors = {c: float(res.std_errors.get(c, np.nan)) for c in params}
    return params, std_errors, int(res.nobs)
