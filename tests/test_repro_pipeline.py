"""Tests for the reproduction pipeline (Steemit -> PSM-DID -> artifacts)."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from onchaingov.collectors.base import RawEvent
from onchaingov.collectors.steemit import SteemitCollector
from onchaingov.reproductions import (
    events_to_panel,
    flatten_steemit_events,
    run_from_steemit_events,
)


def _make_raw_events(tmp_path, *, n_authors: int = 8, n_weeks: int = 6, seed: int = 7):
    import numpy as np

    rng = np.random.default_rng(seed)
    events = []
    treated = set(range(n_authors // 2))
    for ai in range(n_authors):
        for w in range(n_weeks):
            ts = datetime(2024, 3, 1, 12) + timedelta(weeks=w)
            payout = 3.0 + rng.normal(0, 0.5)
            if ai in treated and ts >= datetime(2024, 4, 1):
                payout += 1.5
            events.append(
                RawEvent(
                    source="steemit",
                    event_type="post",
                    entity_id=f"p{ai}_{w}",
                    entity_address=f"a{ai}",
                    timestamp=ts,
                    payload={"author": f"a{ai}", "total_payout_value": f"{payout:.3f} SBD"},
                )
            )
            events.append(
                RawEvent(
                    source="steemit",
                    event_type="vote",
                    entity_id=f"v{ai}_{w}",
                    entity_address=None,
                    timestamp=ts,
                    payload={"voter": f"v{ai}", "weight": 10000 + int(rng.normal(0, 1500))},
                )
            )
    frame = SteemitCollector(tmp_path)._events_to_frame(events)
    path = tmp_path / "steemit_test.parquet"
    frame.write_parquet(path)
    (tmp_path / "treated.txt").write_text(
        "\n".join(f"a{i}" for i in range(n_authors // 2)), encoding="utf-8"
    )
    return tmp_path


def test_flatten_steemit_events(tmp_path):
    _make_raw_events(tmp_path, n_authors=6, n_weeks=4)
    events = pl.read_parquet(tmp_path / "steemit_test.parquet")
    flat = flatten_steemit_events(events)
    assert flat.height == events.height
    assert {"user", "timestamp", "event_type", "payout", "weight"}.issubset(flat.columns)
    # posts carry author payouts, votes carry weights
    posts = flat.filter(pl.col("event_type") == "post")
    votes = flat.filter(pl.col("event_type") == "vote")
    assert (posts["payout"] > 0).all()
    assert (votes["weight"] > 0).all()


def test_flatten_requires_steemit(tmp_path):
    df = pl.DataFrame(
        {
            "source": ["snapshot"],
            "event_type": ["vote"],
            "entity_id": ["v1"],
            "entity_address": ["0x1"],
            "timestamp": [datetime(2024, 1, 1)],
            "payload": ["{}"],
        }
    )
    with pytest.raises(ValueError, match="steemit"):
        flatten_steemit_events(df)


def test_events_to_panel_balanced(tmp_path):
    _make_raw_events(tmp_path, n_authors=6, n_weeks=4)
    events = pl.read_parquet(tmp_path / "steemit_test.parquet")
    flat = flatten_steemit_events(events)
    panel = events_to_panel(flat, freq="week")
    assert "user" in panel.columns
    assert "creation" in panel.columns
    assert "curation" in panel.columns
    # balanced: all users x all weeks
    n_users = flat["user"].n_unique()
    n_periods = panel["period"].n_unique()
    assert panel.height == n_users * n_periods


def test_run_from_steemit_events(tmp_path):
    _make_raw_events(tmp_path)
    out = tmp_path / "repro"
    summary = run_from_steemit_events(
        tmp_path,
        out_dir=out,
        event_time=datetime(2024, 4, 1),
        treated_file=tmp_path / "treated.txt",
        n_placebo=10,
    )
    assert summary["result"] is not None
    assert (out / "reproduction_panel.parquet").exists()
    assert (out / "matched_panel.parquet").exists()
    assert (out / "summary.txt").exists()
    for chart in ("att.png", "event_study.png", "placebo.png"):
        assert (out / chart).exists(), f"missing {chart}"
    # synthetic effect is ~1.5
    assert summary["att"] == pytest.approx(1.5, abs=0.5)


def test_repro_no_steemit_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        run_from_steemit_events(tmp_path / "missing", out_dir=tmp_path / "o")
