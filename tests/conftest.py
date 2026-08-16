"""Shared test fixtures."""

from datetime import datetime, timedelta

import polars as pl


def make_vote_frame() -> pl.DataFrame:
    """A small vote event frame with two spaces."""
    rows = [
        ("snapshot", "vote", "v1", "0xaaa", datetime(2024, 1, 5), 100.0),
        ("snapshot", "vote", "v2", "0xaaa", datetime(2024, 1, 6), 50.0),
        ("snapshot", "vote", "v3", "0xbbb", datetime(2024, 1, 7), 30.0),
        ("snapshot", "vote", "v4", "0xccc", datetime(2024, 1, 8), 20.0),
        ("snapshot", "vote", "v5", "0xccc", datetime(2024, 1, 9), 10.0),
    ]
    return pl.DataFrame(
        {
            "source": [r[0] for r in rows],
            "event_type": [r[1] for r in rows],
            "entity_id": [r[2] for r in rows],
            "entity_address": [r[3] for r in rows],
            "timestamp": [r[4] for r in rows],
            "vp": [r[5] for r in rows],
            "space_id": ["space_a", "space_a", "space_b", "space_a", "space_b"],
        }
    )


def make_proposal_frame() -> pl.DataFrame:
    rows = [
        ("snapshot", "proposal", "p1", "0xaaa", datetime(2024, 1, 1), "space_a"),
        ("snapshot", "proposal", "p2", "0xddd", datetime(2024, 1, 2), "space_a"),
    ]
    return pl.DataFrame(
        {
            "source": [r[0] for r in rows],
            "event_type": [r[1] for r in rows],
            "entity_id": [r[2] for r in rows],
            "entity_address": [r[3] for r in rows],
            "timestamp": [r[4] for r in rows],
            "space_id": [r[5] for r in rows],
        }
    )


def make_panel(treated_effect: float = 2.0, seed: int = 0) -> pl.DataFrame:
    """A balanced synthetic panel for DID testing."""
    import numpy as np

    rng = np.random.default_rng(seed)
    rows = []
    n_units = 60
    n_periods = 10
    event = datetime(2024, 6, 1)
    for i in range(n_units):
        treated = i % 2 == 0
        base = rng.uniform(1.0, 5.0)
        for p in range(n_periods):
            period = event + timedelta(weeks=p - 4)
            post = int(period >= event)
            effect = treated_effect if (treated and post) else 0.0
            rows.append(
                {
                    "unit_id": f"u{i}",
                    "period": period,
                    "treated": int(treated),
                    "post": post,
                    "outcome": base + effect + rng.normal(0, 0.2),
                    "covariate_x": base,
                    "covariate_z": rng.normal(0, 1),
                }
            )
    return pl.DataFrame(rows)
