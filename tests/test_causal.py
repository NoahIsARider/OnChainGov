"""Tests for causal inference templates."""

import polars as pl
import pytest

from onchaingov.causal import (
    did_estimate,
    event_study_estimate,
    in_space_placebo,
    in_time_placebo,
    match_units,
    propensity_scores,
    psm_did_estimate,
)
from tests.conftest import make_panel


def test_did_estimates_effect():
    panel = make_panel(treated_effect=2.0)
    result = did_estimate(panel, outcome="outcome")
    assert result.att == pytest.approx(2.0, abs=0.2)
    assert result.att_pvalue < 0.01


def test_did_zero_effect():
    panel = make_panel(treated_effect=0.0)
    result = did_estimate(panel, outcome="outcome")
    assert result.att == pytest.approx(0.0, abs=0.2)


def test_did_missing_column():
    panel = make_panel()
    panel = panel.drop("post")
    with pytest.raises(ValueError, match="missing"):
        did_estimate(panel, outcome="outcome")


def test_propensity_scores():
    panel = make_panel()
    unit, scores = propensity_scores(panel, covariates=["covariate_x", "covariate_z"])
    assert "pscore" in unit.columns
    assert len(scores) == unit.height
    assert unit["pscore"].is_between(0, 1).all()


def test_propensity_scores_no_covariates_raises():
    panel = make_panel().drop("covariate_x").drop("covariate_z")
    with pytest.raises(ValueError, match="covariates"):
        propensity_scores(panel)


def test_match_units_pairs():
    panel = make_panel()
    unit, _ = propensity_scores(panel, covariates=["covariate_x", "covariate_z"])
    pairs = match_units(unit, caliper=0.2)
    assert len(pairs) > 0
    treated_ids = unit.filter(pl.col("treated") == 1)["unit_id"].to_list()
    control_ids = unit.filter(pl.col("treated") == 0)["unit_id"].to_list()
    for t, c in pairs:
        assert t in treated_ids
        assert c in control_ids


def test_psm_did_runs():
    panel = make_panel(treated_effect=1.5)
    result, match = psm_did_estimate(
        panel,
        outcome="outcome",
        covariates=["covariate_x", "covariate_z"],
        caliper=0.2,
    )
    assert result.model_type == "psm_did"
    assert result.att == pytest.approx(1.5, abs=0.3)
    assert match.matched_n > 0


def test_psm_did_weighted():
    panel = make_panel(treated_effect=1.5)
    _, match = psm_did_estimate(
        panel,
        outcome="outcome",
        covariates=["covariate_x", "covariate_z"],
        caliper=0.2,
        use_weighted_did=True,
    )
    assert "weight" in match.matched_df.columns


def test_in_time_placebo():
    from datetime import datetime

    panel = make_panel(treated_effect=2.0)
    result = in_time_placebo(
        panel,
        outcome="outcome",
        event_time=datetime(2024, 6, 1),
        placebo_times=[datetime(2024, 5, 11), datetime(2024, 5, 25)],
    )
    assert result.test_type == "in_time"
    assert len(result.placebo_estimates) == 2
    assert result.true_att is not None


def test_in_space_placebo():
    panel = make_panel(treated_effect=0.0)
    result = in_space_placebo(panel, outcome="outcome", n_simulations=10, seed=1)
    assert result.test_type == "in_space"
    assert result.n_simulations == 10
    assert 0 <= result.empirical_pvalue <= 1


def test_event_study_runs():
    from datetime import datetime

    panel = make_panel(treated_effect=2.0)
    result = event_study_estimate(
        panel,
        outcome="outcome",
        event_time=datetime(2024, 6, 1),
        n_leads=2,
        n_lags=2,
    )
    assert len(result.relative_periods) > 0
    assert len(result.coefficients) == len(result.relative_periods)
    p = result.pre_trends_pvalue()
    assert 0 <= p <= 1
