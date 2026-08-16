"""Difference-in-Differences (DID) estimator.

Wraps ``linearmodels`` panel two-way fixed effects estimation. Expects a
panel frame in the canonical format with columns:

- ``unit_id``: unit identifier
- ``period``: time period
- ``treated``: 0/1 treatment-group indicator
- ``post``: 0/1 post-treatment indicator
- ``outcome``: outcome variable
- optional covariates and entity/time effects
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl


@dataclass
class DIDResult:
    """Container for DID estimation output."""

    params: dict[str, float]
    std_errors: dict[str, float]
    tstats: dict[str, float]
    pvalues: dict[str, float]
    att: float
    att_std_error: float
    att_pvalue: float
    nobs: int
    model_type: str = "did"
    details: dict[str, Any] = field(default_factory=dict)

    def summary_text(self) -> str:
        """Return a compact textual summary."""
        lines = [
            f"DID estimate (ATT): {self.att:.6f} (se {self.att_std_error:.6f}, p={self.att_pvalue:.4f})",
            f"Observations: {self.nobs}",
        ]
        for name in self.params:
            if name == "treated_post":
                continue
            lines.append(
                f"  {name}: {self.params[name]:.6f} (se {self.std_errors.get(name, float('nan')):.6f})"
            )
        return "\n".join(lines)


def _prep_panel(
    df: pl.DataFrame,
    *,
    treatment: str = "treated",
    post: str = "post",
    outcome: str,
    unit_id: str = "unit_id",
    time_col: str = "period",
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Validate panel and return arrays (treated, post, outcome)."""
    required = {treatment, post, outcome}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"panel missing required columns: {sorted(missing)}")
    treated = df[treatment].to_numpy().astype(np.float64)
    post_arr = df[post].to_numpy().astype(np.float64)
    y = df[outcome].to_numpy().astype(np.float64)
    return treated, post_arr, y


def did_estimate(
    df: pl.DataFrame,
    *,
    outcome: str,
    treatment: str = "treated",
    post: str = "post",
    unit_id: str = "unit_id",
    time_col: str = "period",
    covariates: list[str] | None = None,
) -> DIDResult:
    """Estimate ATT with a two-way fixed effects DID regression.

    Uses ``linearmodels`` PanelOLS with entity and time fixed effects. The
    interaction coefficient (treated x post) is the DID estimator.

    If ``linearmodels`` is unavailable, falls back to a pooled OLS with
    treatment, post, and interaction terms computed via numpy/statsmodels.
    """
    treated, post_arr, _ = _prep_panel(df, treatment=treatment, post=post, outcome=outcome)
    interaction = treated * post_arr

    try:
        return _fit_panel_ols(
            df, outcome=outcome, treatment=treatment, post=post,
            interaction=interaction, unit_id=unit_id, time_col=time_col,
            covariates=covariates,
        )
    except (ImportError, ZeroDivisionError, FloatingPointError, np.linalg.LinAlgError):
        # linearmodels may fail on degenerate panels (e.g. zero residual
        # variance after absorbing fixed effects); fall back to pooled OLS.
        import warnings

        warnings.warn(
            "PanelOLS failed (possibly degenerate panel); falling back to pooled OLS.",
            RuntimeWarning,
            stacklevel=2,
        )
        return _fit_pooled_ols(
            df, outcome=outcome, treatment=treatment, post=post,
            interaction=interaction, covariates=covariates,
        )


def _fit_panel_ols(
    df: pl.DataFrame,
    *,
    outcome: str,
    treatment: str,
    post: str,
    interaction: np.ndarray,
    unit_id: str,
    time_col: str,
    covariates: list[str] | None,
) -> DIDResult:
    import pandas as pd
    from linearmodels.panel import PanelOLS

    pandas_df = df.to_pandas()
    pandas_df["treated_post"] = interaction
    exog_cols = [treatment, post, "treated_post"] + (covariates or [])
    if not isinstance(pandas_df.index, pd.MultiIndex):
        pandas_df = pandas_df.set_index([unit_id, time_col])
    y = pandas_df[outcome]
    X = pandas_df[exog_cols]
    model = PanelOLS(y, X, entity_effects=True, time_effects=True, drop_absorbed=True, check_rank=False)
    res = model.fit(cov_type="clustered", cluster_entity=True)
    params = {c: float(res.params[c]) for c in exog_cols if c in res.params}
    if "treated_post" in params:
        att = params["treated_post"]
        att_se = float(res.std_errors["treated_post"])
        att_p = float(res.pvalues["treated_post"])
    else:
        # treated_post fully absorbed by fixed effects -> zero effect
        att = 0.0
        att_se = float("nan")
        att_p = 1.0
    return DIDResult(
        params=params,
        std_errors={c: float(res.std_errors.get(c, np.nan)) for c in params},
        tstats={c: float(res.tstats.get(c, np.nan)) for c in params},
        pvalues={c: float(res.pvalues.get(c, np.nan)) for c in params},
        att=att,
        att_std_error=att_se,
        att_pvalue=att_p,
        nobs=int(res.nobs),
        model_type="panel_did",
        details={"rsquared": float(res.rsquared)},
    )


def _fit_pooled_ols(
    df: pl.DataFrame,
    *,
    outcome: str,
    treatment: str,
    post: str,
    interaction: np.ndarray,
    covariates: list[str] | None,
) -> DIDResult:
    import statsmodels.api as sm

    columns = {
        "treated": df[treatment].to_numpy().astype(np.float64),
        "post": df[post].to_numpy().astype(np.float64),
        "treated_post": interaction,
    }
    exog_cols = ["treated", "post", "treated_post"]
    if covariates:
        for c in covariates:
            columns[c] = df[c].to_numpy().astype(np.float64)
            exog_cols.append(c)
    X = np.column_stack([columns[c] for c in exog_cols])
    X = sm.add_constant(X)
    y = df[outcome].to_numpy().astype(np.float64)
    model = sm.OLS(y, X).fit(cov_type="HC1")
    idx = ["const"] + exog_cols
    att_idx = idx.index("treated_post")
    att = float(model.params[att_idx])
    att_se = float(model.bse[att_idx])
    att_p = float(model.pvalues[att_idx])
    params = {name: float(model.params[i]) for i, name in enumerate(idx)}
    return DIDResult(
        params=params,
        std_errors={name: float(model.bse[i]) for i, name in enumerate(idx)},
        tstats={name: float(model.tvalues[i]) for i, name in enumerate(idx)},
        pvalues={name: float(model.pvalues[i]) for i, name in enumerate(idx)},
        att=att,
        att_std_error=att_se,
        att_pvalue=att_p,
        nobs=int(model.nobs),
        model_type="pooled_did",
        details={"rsquared": float(model.rsquared)},
    )
