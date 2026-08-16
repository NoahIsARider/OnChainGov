"""End-to-end pipeline test: raw events -> indicators -> panel -> causal -> dataset."""

from datetime import datetime, timedelta

import numpy as np
import polars as pl

from onchaingov.causal import (
    did_estimate,
    event_study_estimate,
    in_space_placebo,
    psm_did_estimate,
)
from onchaingov.export import export_panel
from onchaingov.indicators import participation_metrics
from onchaingov.panel import PanelBuilder, attach_treatment


def _make_raw_events(tmp_path):
    """Raw snapshot-style events with realistic outcome variation."""
    rng = np.random.default_rng(11)
    voters = [f"0x{i:04x}" for i in range(24)]
    treated = set(voters[:12])
    event_time = datetime(2024, 2, 10)
    rows = []
    for w in range(6):
        ts = datetime(2024, 1, 8) + timedelta(weeks=w)
        for v in voters:
            # voters occasionally skip weeks -> panel outcome varies
            if rng.random() < 0.15:
                continue
            effect = 2.0 if (v in treated and ts >= event_time) else 0.0
            rows.append(
                {
                    "source": "snapshot",
                    "event_type": "vote",
                    "entity_id": f"v{w}_{v}",
                    "entity_address": v,
                    "timestamp": ts,
                    "vp": 10.0 + effect + rng.normal(0, 2),
                    "space_id": "space_a",
                }
            )
    raw = pl.DataFrame(rows, schema_overrides={"timestamp": pl.Datetime("us")})
    raw.write_parquet(tmp_path / "raw" / "snapshot_space_a.parquet")
    (tmp_path / "treated.txt").write_text("\n".join(sorted(treated)), encoding="utf-8")
    return raw


def test_full_pipeline(tmp_path):
    tmp_path = tmp_path / "data"
    (tmp_path / "raw").mkdir(parents=True)
    raw = _make_raw_events(tmp_path)

    # indicators
    votes = raw.filter(pl.col("event_type") == "vote")
    ind = participation_metrics(votes, None, group_col="space_id")
    assert ind["voter_count"][0] > 0

    # panel
    builder = PanelBuilder("unit_id", "period", freq="week")
    panel = builder.build(
        raw.rename({"entity_address": "unit_id"}),
        measures={
            "outcome_activity": pl.col("entity_id").count(),
            "outcome_vp": pl.col("vp").sum(),
        },
    )
    panel = attach_treatment(
        panel,
        unit_id="unit_id",
        treated_units=Path_lines(tmp_path / "treated.txt"),
        event_time=datetime(2024, 2, 10),
    )
    # baseline covariates for PSM
    covs = (
        panel.filter(pl.col("period") < datetime(2024, 2, 10))
        .group_by("unit_id")
        .agg(pl.col("outcome_activity").mean().alias("covariate_activity"))
    )
    panel = panel.join(covs, on="unit_id", how="left").with_columns(
        pl.col("covariate_activity").fill_null(0.0)
    )

    # causal inference
    did = did_estimate(panel, outcome="outcome_vp", treatment="treated", post="post")
    assert did.nobs == panel.height
    # in our synthetic design the treatment raises voting power -> positive ATT
    assert did.att > 0

    _, match = psm_did_estimate(
        panel,
        outcome="outcome_vp",
        treatment="treated",
        post="post",
        covariates=["covariate_activity"],
        caliper=0.3,
    )
    assert match.matched_n > 0

    placebo = in_space_placebo(
        panel, outcome="outcome_vp", treatment="treated", post="post", n_simulations=5, seed=1
    )
    assert 0 <= placebo.empirical_pvalue <= 1

    es = event_study_estimate(
        panel,
        outcome="outcome_vp",
        event_time=datetime(2024, 2, 10),
        treatment="treated",
        n_leads=2,
        n_lags=2,
    )
    assert len(es.relative_periods) > 0

    # export
    csv_path = export_panel(panel, tmp_path / "panels" / "panel.csv", fmt="csv")
    assert csv_path.exists()
    parquet_path = export_panel(panel, tmp_path / "panels" / "panel.parquet", fmt="parquet")
    assert parquet_path.exists()

    # dataset publish
    from onchaingov.dataset import publish_dataset

    manifest = publish_dataset(tmp_path, tmp_path / "published", title="e2e", with_csv=True)
    assert (tmp_path / "published" / "dataset.json").exists()
    assert manifest["contents"]["raw"]
    assert manifest["contents"]["panels"]


def Path_lines(p: object):
    return [l.strip() for l in open(p).read().splitlines() if l.strip()]
