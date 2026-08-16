"""Tests for export, schemas, CLI, and reproduction."""

import polars as pl

from onchaingov.export import event_study_chart, export_panel, trend_chart
from onchaingov.normalizers.schemas import event_to_frame
from onchaingov.reproductions import (
    ReproductionConfig,
    run_demo,
    synthesize_steemit_data,
)
from tests.conftest import make_panel


def test_export_parquet(tmp_path):
    panel = make_panel()
    out = export_panel(panel, tmp_path / "p.parquet", fmt="parquet")
    assert out.exists()
    assert pl.read_parquet(out).height == panel.height


def test_export_csv(tmp_path):
    panel = make_panel()
    out = export_panel(panel, tmp_path / "p.csv", fmt="csv")
    assert out.exists()
    assert pl.read_csv(out).height == panel.height


def test_export_invalid_format(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="format"):
        export_panel(make_panel(), tmp_path / "p.xyz", fmt="xyz")


def test_event_to_frame():
    from datetime import datetime

    frame = event_to_frame(
        [{"source": "s", "event_type": "vote", "entity_id": "e1", "timestamp": datetime(2024, 1, 1), "payload": {"vp": 1}}]
    )
    assert frame.height == 1
    assert frame["source"][0] == "s"


def test_trend_chart(tmp_path):
    dates = pl.date_range(pl.datetime(2024, 1, 1), pl.datetime(2024, 1, 7), "1d", eager=True)
    df = pl.DataFrame({"date": dates, "voter_count": list(range(7))})
    out = trend_chart(df, out_path=tmp_path / "trend.png")
    assert out.exists()
    assert out.stat().st_size > 0


def test_event_study_chart(tmp_path):
    out = event_study_chart([-2, -1, 0, 1, 2], [0.1, 0.0, 0.5, 0.6, 0.7], [0.1, 0.1, 0.1, 0.1, 0.1], out_path=tmp_path / "es.png")
    assert out.exists()


def test_synthesize_steemit_data_shape():
    from datetime import datetime

    cfg = ReproductionConfig(
        event_time=datetime(2024, 7, 1),
        n_units=50,
        n_periods=6,
    )
    panel = synthesize_steemit_data(cfg)
    assert panel.height == 300
    assert "treated" in panel.columns
    assert "post" in panel.columns
    assert panel["treated"].sum() == 25 * 6


def test_run_demo(tmp_path):
    summary = run_demo(out_dir=tmp_path / "repro")
    assert summary["result"] is not None
    assert (tmp_path / "repro" / "summary.txt").exists()
    assert (tmp_path / "repro" / "reproduction_panel.parquet").exists()
    assert (tmp_path / "repro" / "matched_panel.parquet").exists()
