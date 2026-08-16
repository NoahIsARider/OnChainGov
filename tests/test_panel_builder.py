"""Tests for the panel builder."""

from datetime import datetime

import polars as pl
import pytest

from onchaingov.panel import PanelBuilder, attach_treatment


def _events() -> pl.DataFrame:
    rows = []
    t0 = datetime(2024, 1, 1)
    for u in ("a", "b"):
        for day in range(14):
            rows.append(
                {
                    "entity_address": u,
                    "timestamp": t0.replace(day=day + 1),
                    "entity_id": f"{u}-{day}",
                }
            )
    return pl.DataFrame(rows)


def test_panel_build_counts():
    events = _events()
    builder = PanelBuilder(unit_id="user", freq="week")
    panel = builder.build(events)
    assert panel["user"].n_unique() == 2
    assert "period" in panel.columns
    assert "count" in panel.columns
    # each user active in both weeks
    assert panel["count"].min() > 0


def test_panel_build_measures():
    events = pl.DataFrame(
        {
            "entity_address": ["a", "a", "b"],
            "timestamp": [datetime(2024, 1, 1)] * 3,
            "entity_id": ["1", "2", "3"],
        }
    )
    builder = PanelBuilder(unit_id="user", freq="week")
    panel = builder.build(
        events,
        measures={"distinct_voters": pl.col("entity_address").n_unique()},
    )
    assert "distinct_voters" in panel.columns
    a = panel.filter(pl.col("user") == "a")
    assert a["distinct_voters"][0] == 1


def test_panel_build_fill_zeros():
    events = _events()
    builder = PanelBuilder(unit_id="user", freq="week")
    # user "b" has no activity in second week -> fill zero
    events2 = events.filter(~((pl.col("entity_address") == "b") & (pl.col("timestamp") >= datetime(2024, 1, 8))))
    panel = builder.build(events2)
    b_week2 = panel.filter((pl.col("user") == "b") & (pl.col("period") >= datetime(2024, 1, 8)))
    assert b_week2["count"][0] == 0.0


def test_panel_build_invalid_freq():
    with pytest.raises(ValueError, match="freq"):
        PanelBuilder(freq="year")


def test_panel_build_empty_raises():
    builder = PanelBuilder()
    with pytest.raises(ValueError, match="empty"):
        builder.build(pl.DataFrame({"a": []}))


def test_attach_treatment():
    events = _events()
    panel = PanelBuilder(unit_id="user", freq="week").build(events)
    treated = attach_treatment(
        panel,
        unit_id="user",
        treated_units=["a"],
        event_time=datetime(2024, 1, 8),
    )
    assert "treated" in treated.columns
    assert "post" in treated.columns
    a = treated.filter(pl.col("user") == "a")
    assert a["treated"].unique().to_list() == [1]
    b = treated.filter(pl.col("user") == "b")
    assert b["treated"].unique().to_list() == [0]
    # post flips at event time
    before = a.filter(pl.col("period") < datetime(2024, 1, 8))
    after = a.filter(pl.col("period") >= datetime(2024, 1, 8))
    assert before["post"].unique().to_list() == [0]
    assert after["post"].unique().to_list() == [1]
