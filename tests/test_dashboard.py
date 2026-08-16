"""Smoke tests for the Streamlit dashboard and the CLI wiring."""

from pathlib import Path

import polars as pl
import pytest

streamlit = pytest.importorskip("streamlit")


def test_dashboard_module_loads():
    from onchaingov.dashboard import APP_PATH

    assert Path(APP_PATH).exists()
    import importlib.util

    spec = importlib.util.spec_from_file_location("dash_app", APP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert callable(mod.main)
    assert hasattr(mod, "overview_page")


def test_dashboard_panel_helpers(tmp_path):
    from onchaingov.dashboard.app import _load_first, _parquet_files

    (tmp_path / "raw").mkdir(parents=True)
    pl.DataFrame({"a": [1, 2]}).write_parquet(tmp_path / "raw" / "x.parquet")
    files = _parquet_files(tmp_path, "raw")
    assert len(files) == 1
    df = _load_first(tmp_path, "raw")
    assert df is not None and df.height == 2
    assert _load_first(tmp_path, "missing") is None


def test_cli_dashboard_command_builds():


    # do not actually launch; just ensure the parser wiring accepts flags
    from onchaingov.cli import _build_parser

    args = _build_parser().parse_args(["dashboard", "--data-dir", "data", "--port", "8501"])
    assert args.command == "dashboard"
    assert args.data_dir == "data"
    assert args.port == 8501
