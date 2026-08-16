"""Panel data builder.

Constructs balanced unit-time panel frames from event data. Supports
unit-level aggregation of counts, sums, and arbitrary indicator columns.

The canonical output format (used by the causal inference templates):

    unit_id, period, treated, post, outcome_*, covariate_*, weight
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import polars as pl

PERIOD_FREQ = {"day": "1d", "week": "1w", "month": "1mo"}


class PanelBuilder:
    """Build a unit-period panel from a long-format events frame."""

    def __init__(
        self,
        unit_id: str = "unit_id",
        time: str = "period",
        *,
        freq: str = "week",
    ) -> None:
        if freq not in PERIOD_FREQ:
            raise ValueError(f"freq must be one of {sorted(PERIOD_FREQ)}")
        self.unit_id = unit_id
        self.time = time
        self.freq = freq

    def build(
        self,
        events: pl.DataFrame,
        *,
        measures: dict[str, pl.Expr] | None = None,
        min_period: datetime | str | None = None,
        max_period: datetime | str | None = None,
        fill: bool = True,
    ) -> pl.DataFrame:
        """Build a balanced panel.

        Args:
            events: Long event frame with ``timestamp`` and an ``entity_address``
                (or user-specified unit) column.
            measures: Mapping of output column name -> polars aggregation
                expression. Defaults to an event count.
            min_period / max_period: Panel time bounds.
            fill: Fill missing unit-period cells with zeros.

        Returns:
            Balanced panel DataFrame keyed by (unit_id, period).
        """
        if events.is_empty():
            raise ValueError("events frame is empty")

        unit_col = self.unit_id
        # determine unit column if not present, use entity_address fallback
        if unit_col not in events.columns:
            for candidate in ("entity_address", "author", "voter"):
                if candidate in events.columns:
                    unit_col = candidate
                    break
            else:
                raise ValueError(f"no unit column found in events frame (need {self.unit_id!r})")

        df = events.with_columns(
            pl.col("timestamp").dt.truncate(PERIOD_FREQ[self.freq]).alias(self.time)
        )

        if min_period is not None:
            minp = self._as_dt(min_period)
            df = df.filter(pl.col("timestamp") >= minp)
        if max_period is not None:
            maxp = self._as_dt(max_period)
            df = df.filter(pl.col("timestamp") <= maxp)

        if measures is None:
            panel = (
                df.group_by([unit_col, self.time])
                .agg(pl.col("entity_id").count().alias("count"))
            )
        else:
            panel = df.group_by([unit_col, self.time]).agg(**measures)

        if unit_col != self.unit_id:
            panel = panel.rename({unit_col: self.unit_id})

        if fill:
            panel = self._fill_zeros(panel)

        return panel.sort([self.unit_id, self.time])

    def _fill_zeros(self, panel: pl.DataFrame) -> pl.DataFrame:
        """Fill missing unit-period combinations with zeros for numeric cols."""
        units = panel[self.unit_id].unique().sort().to_list()
        periods = panel[self.time].unique().sort().to_list()

        grid = pl.DataFrame(
            {
                self.unit_id: [u for u in units for _ in periods],
                self.time: [p for _ in units for p in periods],
            },
            schema={self.unit_id: panel[self.unit_id].dtype, self.time: panel[self.time].dtype},
        ).sort([self.unit_id, self.time])
        merged = grid.join(panel, on=[self.unit_id, self.time], how="left")
        numeric = (pl.Float64, pl.Float32, pl.Int64, pl.Int32, pl.Int16, pl.Int8, pl.UInt32, pl.UInt16, pl.UInt8)
        for col in merged.columns:
            if col in (self.unit_id, self.time):
                continue
            if merged[col].dtype in numeric:
                merged = merged.with_columns(pl.col(col).fill_null(0).alias(col))
        return merged

    @staticmethod
    def _as_dt(value: datetime | str) -> datetime:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value.replace("Z", "+00:00"))


def attach_treatment(
    panel: pl.DataFrame,
    *,
    unit_id: str = "unit_id",
    treated_units: Iterable[str],
    event_time: datetime | str,
    time_col: str = "period",
    post_col: str = "post",
    treated_col: str = "treated",
) -> pl.DataFrame:
    """Attach DID treatment indicators to a panel.

    Args:
        panel: Unit-period panel.
        treated_units: Set of unit ids in the treatment group.
        event_time: Time at which treatment begins (post-period starts).
        time_col: The period column name.

    Returns:
        Panel with ``treated`` and ``post`` indicator columns.
    """
    event = PanelBuilder._as_dt(event_time) if isinstance(event_time, str) else event_time
    treated_set = set(treated_units)
    return panel.with_columns(
        pl.col(unit_id)
        .is_in(treated_set)
        .cast(pl.Int8)
        .alias(treated_col),
        (pl.col(time_col) >= event).cast(pl.Int8).alias(post_col),
    )
