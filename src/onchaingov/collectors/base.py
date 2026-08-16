"""Collector base classes and data models."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl


@dataclass
class RawEvent:
    """A single raw governance event collected from a data source."""

    source: str
    event_type: str
    entity_id: str
    timestamp: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    entity_address: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to a JSON-serializable dict."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


class Collector(ABC):
    """Base class for all data collectors.

    Subclasses implement :meth:`run` and produce a list of :class:`RawEvent`.
    """

    source_name: str = "base"

    def __init__(self, out_dir: str | Path | None = None) -> None:
        self.out_dir = Path(out_dir) if out_dir else None

    @abstractmethod
    def run(self, **kwargs: Any) -> list[RawEvent]:
        """Execute collection and return the collected events."""
        raise NotImplementedError

    def save(self, events: list[RawEvent], *, name: str | None = None) -> Path:
        """Serialize events to a Parquet file under the output directory.

        Raises:
            ValueError: if no output directory was configured.
        """
        if self.out_dir is None:
            raise ValueError("out_dir is not configured for this collector")
        df = self._events_to_frame(events)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        tag = name or f"{self.source_name}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        path = self.out_dir / f"{tag}.parquet"
        df.write_parquet(path)
        return path

    @staticmethod
    def _events_to_frame(events: list[RawEvent]) -> pl.DataFrame:
        if not events:
            return pl.DataFrame(
                {
                    "source": [],
                    "event_type": [],
                    "entity_id": [],
                    "entity_address": [],
                    "timestamp": [],
                    "payload": [],
                    "raw": [],
                },
                schema={
                    "source": pl.String,
                    "event_type": pl.String,
                    "entity_id": pl.String,
                    "entity_address": pl.String,
                    "timestamp": pl.Datetime("us"),
                    "payload": pl.String,
                    "raw": pl.String,
                },
            )
        rows = []
        for ev in events:
            rows.append(
                {
                    "source": ev.source,
                    "event_type": ev.event_type,
                    "entity_id": ev.entity_id,
                    "entity_address": ev.entity_address,
                    "timestamp": ev.timestamp,
                    "payload": json.dumps(ev.payload, default=str),
                    "raw": json.dumps(ev.raw, default=str),
                }
            )
        return pl.DataFrame(rows, strict=False)
