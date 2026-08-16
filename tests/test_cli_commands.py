"""CLI command tests for the v2/v3 surface (reproduce, attach-treatment, dataset)."""

from datetime import datetime

import polars as pl
import pytest

from onchaingov.cli import main


def test_cli_reproduce_demo(tmp_path):
    rc = main(["reproduce", "jom2025", "--demo", "--out", str(tmp_path), "--placebo", "5"])
    assert rc == 0
    assert (tmp_path / "summary.txt").exists()
    assert (tmp_path / "matched_panel.parquet").exists()


def test_cli_attach_treatment(tmp_path):
    panel = pl.DataFrame(
        {
            "unit_id": ["u1", "u1", "u2", "u2"],
            "period": [datetime(2024, 1, 1), datetime(2024, 1, 8), datetime(2024, 1, 1), datetime(2024, 1, 8)],
            "outcome": [1.0, 2.0, 3.0, 4.0],
        }
    )
    panel_path = tmp_path / "panel.parquet"
    panel.write_parquet(panel_path)
    (tmp_path / "treated.txt").write_text("u1\n", encoding="utf-8")
    out_path = tmp_path / "panel_treated.parquet"
    rc = main(
        [
            "attach-treatment",
            "--panel", str(panel_path),
            "--treated-file", str(tmp_path / "treated.txt"),
            "--event-time", "2024-01-04T00:00:00",
            "--out", str(out_path),
        ]
    )
    assert rc == 0
    out = pl.read_parquet(out_path)
    assert "treated" in out.columns
    assert "post" in out.columns
    assert out.filter(pl.col("unit_id") == "u1")["treated"].to_list() == [1, 1]
    assert out.filter(pl.col("unit_id") == "u2")["treated"].to_list() == [0, 0]


def test_cli_dataset_publish(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    pl.DataFrame(
        {"source": ["snapshot"], "event_type": ["vote"], "entity_id": ["v"],
         "entity_address": ["0x1"], "timestamp": [datetime(2024, 1, 1)]}
    ).write_parquet(raw / "r.parquet")
    out = tmp_path / "published"
    rc = main(
        [
            "dataset", "publish",
            "--data-dir", str(tmp_path),
            "--out", str(out),
            "--title", "T",
        ]
    )
    assert rc == 0
    assert (out / "dataset.json").exists()
    assert (out / "README.md").exists()


def test_cli_dataset_info(tmp_path, capsys):
    raw = tmp_path / "raw"
    raw.mkdir()
    pl.DataFrame({"a": [1]}).write_parquet(raw / "r.parquet")
    rc = main(["dataset", "info", "--data-dir", str(tmp_path)])
    assert rc == 0
    assert "r.parquet" in capsys.readouterr().out


def test_cli_unknown_source_errors(tmp_path):
    with pytest.raises(SystemExit):
        main(["collect", "unknown"])


def test_cli_did_missing_panel_file(tmp_path):
    rc = main(["did", "--panel", str(tmp_path / "nope.parquet"), "--outcome", "x"])
    assert rc == 1
