"""Reproduction of the JOM 2025 Steemit governance-token study.

This module provides a reproducible pipeline mirroring the estimation
strategy of the JOM 2025 paper (governance token vs. tradeable token
incentive effects on the Steemit platform): construct a user-level panel
of token incentives (creation / curation / novelty / ownership share) and
run PSM-DID to estimate the differential effect.

The pipeline is data-driven: it reads already-collected Steemit event
frames and runs the estimation. A synthetic-data demo is included for
smoke-testing the pipeline end to end. Output artifacts include the panel,
the matched sample, a text summary, and paper charts (event study,
placebo distribution, ATT with confidence interval).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl

from onchaingov.causal.placebo import in_space_placebo
from onchaingov.causal.psm_did import psm_did_estimate
from onchaingov.export import event_study_chart, placebo_distribution_chart
from onchaingov.indicators.token_incentive import _parse_payout
from onchaingov.panel.builder import PanelBuilder


@dataclass
class ReproductionConfig:
    """Configuration for the JOM 2025 reproduction pipeline."""

    event_time: datetime
    treated_share: float = 0.5
    outcome_col: str = "creation"
    caliper: float = 0.05
    n_units: int = 200
    n_periods: int = 12


def synthesize_steemit_data(cfg: ReproductionConfig) -> pl.DataFrame:
    """Generate synthetic Steemit-style panel data for a smoke test.

    Generates a balanced user-period panel with:

    - ``unit_id``, ``period``, ``treated``, ``post``
    - ``creation`` / ``curation`` / ``novelty`` / ``ownership_share``
      incentive dimensions
    - a treatment effect on ``creation`` for treated users post-event.

    Args:
        cfg: Reproduction configuration.

    Returns:
        A long-format panel DataFrame.
    """
    rng = np.random.default_rng(42)
    rows: list[dict] = []
    n_treated = int(cfg.n_units * cfg.treated_share)
    for i in range(cfg.n_units):
        is_treated = i < n_treated
        base_creation = rng.uniform(0.5, 5.0)
        base_curation = rng.uniform(0.2, 3.0)
        for p in range(cfg.n_periods):
            period = cfg.event_time + timedelta(weeks=p - cfg.n_periods // 2)
            post = int(period >= cfg.event_time)
            effect = 2.0 if (is_treated and post) else 0.0
            rows.append(
                {
                    "unit_id": f"u{i}",
                    "period": period,
                    "treated": int(is_treated),
                    "post": post,
                    "creation": base_creation + effect + rng.normal(0, 0.3),
                    "curation": base_curation + rng.normal(0, 0.2),
                    "novelty": rng.uniform(0.1, 2.0),
                    "ownership_share": rng.uniform(0.0, 0.05),
                    "covariate_age": base_creation,
                    "covariate_curation": base_curation,
                }
            )
    return pl.DataFrame(rows)


def run_reproduction(
    panel: pl.DataFrame,
    cfg: ReproductionConfig,
    *,
    covariates: list[str] | None = None,
    n_placebo: int = 100,
    seed: int = 42,
    diagnostics: bool = True,
) -> dict:
    """Run the PSM-DID reproduction on a panel.

    Returns a dict with the DID result, match info, and (optionally) the
    event-study and in-space placebo diagnostics ready for a notebook.
    """
    from onchaingov.causal.event_study import event_study_estimate

    covs = covariates or [
        c for c in ("covariate_age", "covariate_curation") if c in panel.columns
    ]
    result, match = psm_did_estimate(
        panel,
        outcome=cfg.outcome_col,
        treatment="treated",
        post="post",
        unit_id="unit_id",
        time_col="period",
        covariates=covs,
        caliper=cfg.caliper,
    )
    out: dict = {
        "result": result,
        "match": match,
        "config": cfg,
        "att": result.att,
        "att_pvalue": result.att_pvalue,
        "matched_units": match.matched_n,
    }
    if diagnostics and match.matched_df.height > 0:
        event_study = event_study_estimate(
            match.matched_df,
            outcome=cfg.outcome_col,
            event_time=cfg.event_time,
            treatment="treated",
            unit_id="unit_id",
            time_col="period",
        )
        placebo = in_space_placebo(
            match.matched_df,
            outcome=cfg.outcome_col,
            treatment="treated",
            post="post",
            unit_id="unit_id",
            time_col="period",
            covariates=covs,
            n_simulations=n_placebo,
            seed=seed,
        )
        out["event_study"] = event_study
        out["placebo"] = placebo
    return out


def run_demo(
    out_dir: str | Path = "data/reproductions/jom2025",
    *,
    n_placebo: int = 100,
) -> dict:
    """Run the full JOM 2025 reproduction demo with synthetic data.

    Writes the panel, matched sample, propensity scores, a text summary,
    and paper charts to ``out_dir``.
    """
    cfg = ReproductionConfig(
        event_time=datetime(2024, 7, 1),
        treated_share=0.5,
        n_units=300,
        n_periods=14,
    )
    panel = synthesize_steemit_data(cfg)
    summary = run_reproduction(panel, cfg, n_placebo=n_placebo)
    return write_artifacts(summary, panel, out_dir)


def events_to_panel(
    events: pl.DataFrame,
    *,
    unit_col: str = "user",
    freq: str = "week",
) -> pl.DataFrame:
    """Build a user-period incentive panel from flattened Steemit events.

    Expects a frame with columns ``user``, ``timestamp``, ``event_type``,
    ``payout`` (creation reward per post) and ``weight`` (curation vote
    weight per vote). Returns a balanced panel with columns
    ``user``, ``period``, ``post_count``, ``vote_count``, ``creation``,
    ``curation``.
    """
    if events.is_empty():
        raise ValueError("events frame is empty")
    builder = PanelBuilder(unit_col, "period", freq=freq)
    measures = {
        "post_count": pl.col("event_type").filter(pl.col("event_type") == "post").count(),
        "vote_count": pl.col("event_type").filter(pl.col("event_type") == "vote").count(),
        "creation": pl.col("payout").sum(),
        "curation": pl.col("weight").sum(),
    }
    return builder.build(events, measures=measures)


def _payload_field(payload: object, field: str) -> object:
    """Extract a field from a JSON-string payload column value."""
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload.get(field)
    try:
        return json.loads(payload).get(field)
    except (ValueError, TypeError, AttributeError):
        return None


def flatten_steemit_events(events: pl.DataFrame) -> pl.DataFrame:
    """Flatten raw Steemit collector output into an incentive frame.

    Reads the normalized event frame written by ``SteemitCollector`` and
    returns a frame with columns ``user``, ``timestamp``, ``event_type``,
    ``payout``, ``weight`` usable by ``events_to_panel``.
    """
    if events.is_empty():
        raise ValueError("events frame is empty")
    df = events.filter(pl.col("source") == "steemit")
    if df.is_empty():
        raise ValueError("no steemit events found; collect with `onchaingov collect steemit` first")

    def _payout(payload: object) -> float:
        return _parse_payout(_payload_field(payload, "total_payout_value"))

    def _weight(payload: object) -> float:
        return _parse_payout(_payload_field(payload, "weight"))

    def _field_str(payload: object, field: str) -> str:
        value = _payload_field(payload, field)
        return "" if value is None else str(value)

    df = df.with_columns(
        pl.col("payload").map_elements(_payout, return_dtype=pl.Float64).alias("payout"),
        pl.col("payload").map_elements(_weight, return_dtype=pl.Float64).alias("weight"),
        pl.when(pl.col("event_type") == "vote")
        .then(pl.col("payload").map_elements(lambda p: _field_str(p, "voter"), return_dtype=pl.String))
        .otherwise(pl.col("entity_address"))
        .alias("user"),
    )
    return df.select(
        "user",
        "timestamp",
        "event_type",
        "payout",
        "weight",
    ).filter(pl.col("user").is_not_null() & (pl.col("user") != ""))


def run_from_steemit_events(
    data_dir: str | Path,
    out_dir: str | Path = "data/reproductions/jom2025",
    *,
    event_time: datetime | None = None,
    treated_file: str | Path | None = None,
    n_placebo: int = 100,
    freq: str = "week",
    caliper: float = 0.05,
) -> dict:
    """Run the reproduction on already-collected Steemit event data.

    Args:
        data_dir: Directory containing Steemit collector Parquet output.
        out_dir: Directory for reproduction artifacts.
        event_time: Treatment event time; defaults to the median period.
        treated_file: Optional file of treated user ids (one per line).
        n_placebo: Number of in-space placebo simulations.
        freq: Panel period frequency (day/week/month).
        caliper: PSM caliper; widened automatically if matching finds nothing.

    Raises:
        ValueError: if no steemit events or no treated units are found.
    """
    paths = sorted(Path(data_dir).glob("*.parquet"))
    if not paths:
        raise FileNotFoundError(f"no parquet files under {data_dir}")
    events = pl.concat([pl.read_parquet(p) for p in paths], how="diagonal_relaxed")
    flat = flatten_steemit_events(events)
    panel = events_to_panel(flat, freq=freq)

    if event_time is None:
        mid = panel["period"].min() + (panel["period"].max() - panel["period"].min()) / 2
        event_time = mid
    event_time = event_time.replace(tzinfo=None) if event_time.tzinfo else event_time

    if treated_file is not None:
        treated_units = [
            line.strip()
            for line in Path(treated_file).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        # Fall back to the top half of users by average creation reward.
        top = (
            panel.group_by("user")
            .agg(pl.col("creation").mean().alias("avg_creation"))
            .sort("avg_creation", descending=True)
        )
        treated_units = top["user"].head(max(1, top.height // 2)).to_list()
    if not treated_units:
        raise ValueError("no treated units identified")

    panel = panel.with_columns(
        pl.col("user").is_in(set(treated_units)).cast(pl.Int8).alias("treated"),
        (pl.col("period") >= event_time).cast(pl.Int8).alias("post"),
    )
    panel = panel.rename({"user": "unit_id"})

    cfg = ReproductionConfig(
        event_time=event_time,
        outcome_col="creation",
        caliper=caliper,
    )
    # Add unit-level baseline covariates for the propensity score.
    covs = ["covariate_creation", "covariate_curation"]
    baseline = (
        panel.filter(pl.col("period") < event_time)
        .group_by("unit_id")
        .agg(
            pl.col("creation").mean().alias("covariate_creation"),
            pl.col("curation").mean().alias("covariate_curation"),
        )
    )
    panel = panel.join(baseline, on="unit_id", how="left")

    try:
        summary = run_reproduction(panel, cfg, covariates=covs, n_placebo=n_placebo)
    except ValueError as exc:
        if "no matches" not in str(exc):
            raise
        # Widen the caliper and retry once; the score distribution may be tight.
        cfg = ReproductionConfig(
            event_time=event_time,
            outcome_col="creation",
            caliper=max(caliper, 0.2),
        )
        summary = run_reproduction(panel, cfg, covariates=covs, n_placebo=n_placebo)
    return write_artifacts(summary, panel, out_dir)


def write_artifacts(
    summary: dict,
    panel: pl.DataFrame,
    out_dir: str | Path,
) -> dict:
    """Write reproduction artifacts (data + text summary + paper charts)."""
    from onchaingov.export import export_panel

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    export_panel(panel, out_dir / "reproduction_panel.parquet", fmt="parquet")
    export_panel(summary["match"].matched_df, out_dir / "matched_panel.parquet", fmt="parquet")
    scores = summary["match"].propensity_scores
    if scores is not None and scores.height > 0:
        export_panel(scores, out_dir / "propensity_scores.parquet", fmt="parquet")

    lines = [
        "JOM 2025 reproduction (governance token vs. tradeable token incentives)",
        "-----------------------------------------------------------------------",
        (
            f"ATT on {summary['config'].outcome_col}: {summary['att']:.6f} "
            f"(p={summary['att_pvalue']:.4f})"
        ),
        f"Matched sample: {summary['matched_units']} rows",
    ]
    event_study = summary.get("event_study")
    if event_study is not None:
        lines.append(
            f"Event study: {len(event_study.relative_periods)} relative periods, "
            f"pre-trends p-value {event_study.pre_trends_pvalue():.4f}"
        )
    placebo = summary.get("placebo")
    if placebo is not None:
        lines.append(
            f"In-space placebo: mean pseudo-ATT {placebo.mean_placebo:.6f}, "
            f"empirical p-value {placebo.empirical_pvalue:.4f} (passed={placebo.passed()})"
        )
    (out_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Paper charts
    if event_study is not None:
        event_study_chart(
            event_study.relative_periods,
            event_study.coefficients,
            event_study.std_errors,
            out_path=out_dir / "event_study.png",
            title="JOM 2025 reproduction: dynamic treatment effects",
        )
    if placebo is not None:
        placebo_distribution_chart(
            placebo.placebo_estimates,
            out_path=out_dir / "placebo.png",
            true_att=summary["att"],
            title="JOM 2025 reproduction: in-space placebo distribution",
        )
    _att_chart(summary, out_dir)
    return summary


def _att_chart(summary: dict, out_dir: Path) -> None:
    """Bar chart of the reproduction ATT with a 95% confidence interval."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    att = summary["att"]
    se = summary["result"].att_std_error
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(["ATT"], [att], yerr=1.96 * se if np.isfinite(se) else None, capsize=5, color="#4C72B0")
    ax.axhline(0, color="black", lw=0.8, ls="--")
    ax.set_title(f"PSM-DID ATT on {summary['config'].outcome_col}")
    ax.set_ylabel("Estimate")
    ax.grid(alpha=0.3)
    fig.savefig(out_dir / "att.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
