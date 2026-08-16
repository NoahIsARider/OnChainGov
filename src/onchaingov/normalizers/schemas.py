"""Normalization schemas and loaders for collected governance data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

# Required columns for a normalized event frame
EVENT_SCHEMA: dict[str, pl.DataType] = {
    "source": pl.String,
    "event_type": pl.String,
    "entity_id": pl.String,
    "entity_address": pl.String,
    "timestamp": pl.Datetime("us"),
    "payload": pl.String,
}


def load_raw_events(path: str | Path) -> pl.DataFrame:
    """Load a raw events Parquet file into a DataFrame."""
    df = pl.read_parquet(path)
    return df


def load_all_raw(paths: list[str | Path]) -> pl.DataFrame:
    """Load and concatenate multiple raw event files."""
    frames = [load_raw_events(p) for p in paths]
    if not frames:
        raise ValueError("no raw event files provided")
    return pl.concat(frames, how="diagonal_relaxed")


def event_to_frame(events: list[Any]) -> pl.DataFrame:
    """Convert a list of event dicts (or RawEvent) to a normalized frame."""
    rows = []
    for ev in events:
        if hasattr(ev, "to_dict"):
            d = ev.to_dict()
        else:
            d = ev
        rows.append(
            {
                "source": d.get("source", ""),
                "event_type": d.get("event_type", ""),
                "entity_id": d.get("entity_id", ""),
                "entity_address": d.get("entity_address"),
                "timestamp": d.get("timestamp"),
                "payload": json.dumps(d.get("payload", {}), default=str),
            }
        )
    return pl.DataFrame(rows, schema_overrides=EVENT_SCHEMA, strict=False)


def write_parquet(df: pl.DataFrame, path: str | Path) -> Path:
    """Write a DataFrame to Parquet, creating parent dirs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)
    return path


def write_csv(df: pl.DataFrame, path: str | Path) -> Path:
    """Write a DataFrame to CSV, creating parent dirs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_csv(path)
    return path
