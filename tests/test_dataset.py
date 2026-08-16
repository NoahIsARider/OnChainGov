"""Tests for dataset assembly and publishing."""

import json
from datetime import datetime

import polars as pl

from onchaingov.dataset import (
    _checksum,
    build_manifest,
    publish_dataset,
    summarize_data_dir,
)


def _make_tree(tmp_path):
    raw = tmp_path / "raw"
    panels = tmp_path / "panels"
    indicators = tmp_path / "indicators"
    raw.mkdir()
    panels.mkdir()
    indicators.mkdir()
    pl.DataFrame(
        {
            "source": ["snapshot"],
            "event_type": ["vote"],
            "entity_id": ["v1"],
            "entity_address": ["0x1"],
            "timestamp": [datetime(2024, 1, 1)],
            "vp": [10.0],
        }
    ).write_parquet(raw / "raw.parquet")
    pl.DataFrame(
        {"unit_id": ["u1", "u2"], "period": [1, 2], "outcome": [0.5, 1.0]}
    ).write_parquet(panels / "panel.parquet")
    pl.DataFrame({"space_id": ["a"], "voter_count": [5]}).write_parquet(
        indicators / "ind.parquet"
    )
    return tmp_path


def test_summarize_data_dir(tmp_path):
    _make_tree(tmp_path)
    summary = summarize_data_dir(tmp_path)
    assert len(summary["raw"]) == 1
    assert len(summary["panels"]) == 1
    assert len(summary["indicators"]) == 1
    assert summary["raw"][0]["rows"] == 1


def test_build_manifest(tmp_path):
    _make_tree(tmp_path)
    manifest = build_manifest(tmp_path, title="My dataset", version="2.0.0")
    assert manifest["name"] == "My dataset"
    assert manifest["version"] == "2.0.0"
    assert manifest["toolchain"]["name"] == "onchaingov"
    assert "raw" in manifest["contents"]


def test_publish_dataset(tmp_path):
    _make_tree(tmp_path)
    out = tmp_path / "published"
    manifest = publish_dataset(
        tmp_path,
        out,
        title="Demo",
        authors=["Alice"],
        with_csv=True,
    )
    assert (out / "dataset.json").exists()
    assert (out / "README.md").exists()
    assert (out / "raw" / "raw.parquet").exists()
    assert (out / "raw" / "raw.csv").exists()
    assert (out / "panels" / "panel.parquet").exists()
    assert manifest["files"]["raw"][0]["sha256"] == _checksum(out / "raw" / "raw.parquet")
    loaded = json.loads((out / "dataset.json").read_text(encoding="utf-8"))
    assert loaded["name"] == "Demo"
    assert loaded["version"] == "0.1.0"


def test_publish_dataset_none_version_defaults(tmp_path):
    _make_tree(tmp_path)
    manifest = publish_dataset(tmp_path, tmp_path / "pub", version=None)
    assert manifest["version"] == "0.1.0"


def test_checksum_stable(tmp_path):
    _make_tree(tmp_path)
    f = tmp_path / "raw" / "raw.parquet"
    assert _checksum(f) == _checksum(f)


def test_summarize_empty_dir(tmp_path):
    summary = summarize_data_dir(tmp_path)
    assert all(v == [] for v in summary.values())
