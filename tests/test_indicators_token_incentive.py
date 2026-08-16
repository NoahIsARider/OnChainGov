"""Tests for token incentive metrics."""

import polars as pl
import pytest

from onchaingov.indicators import (
    creation_metric,
    curation_metric,
    novelty_metric,
    ownership_share,
)


def test_creation_metric_sums_payouts():
    t = pl.Series(["2024-01-01"]).str.to_datetime()[0]
    posts = pl.DataFrame(
        {
            "author": ["alice", "alice", "bob"],
            "entity_id": ["p1", "p2", "p3"],
            "total_payout_value": ["10.0 SBD", "5.0 SBD", "2.0 SBD"],
            "timestamp": [t] * 3,
        }
    )
    out = creation_metric(posts)
    alice = out.filter(pl.col("author") == "alice")
    assert alice["creation"][0] == pytest.approx(15.0)
    assert alice["post_count"][0] == 2


def test_creation_metric_empty():
    out = creation_metric(
        pl.DataFrame({"author": [], "entity_id": [], "total_payout_value": [], "timestamp": []})
    )
    assert out.is_empty()


def test_curation_metric():
    votes = pl.DataFrame(
        {
            "voter": ["carol", "carol", "dave"],
            "weight": [100.0, 50.0, 30.0],
        }
    )
    out = curation_metric(votes)
    carol = out.filter(pl.col("voter") == "carol")
    assert carol["curation"][0] == pytest.approx(150.0)


def test_novelty_metric_gap():
    events = pl.DataFrame(
        {
            "entity_address": ["u1", "u1", "u1"],
            "timestamp": [
                pl.Series(["2024-01-01"]).str.to_datetime()[0],
                pl.Series(["2024-01-02"]).str.to_datetime()[0],
                pl.Series(["2024-01-04"]).str.to_datetime()[0],
            ],
        }
    )
    out = novelty_metric(events)
    row = out.filter(pl.col("entity_address") == "u1")
    assert row["novelty"][0] == pytest.approx(1.5)
    assert row["first_time"][0] == 0


def test_novelty_first_time_flag():
    events = pl.DataFrame(
        {
            "entity_address": ["u2"],
            "timestamp": [pl.Series(["2024-01-01"]).str.to_datetime()[0]],
        }
    )
    out = novelty_metric(events)
    assert out["first_time"][0] == 1


def test_ownership_share():
    holdings = pl.DataFrame(
        {
            "entity_address": ["a", "b", "c"],
            "amount": [70.0, 20.0, 10.0],
            "space_id": ["s1", "s1", "s1"],
        }
    )
    out = ownership_share(holdings)
    assert out["ownership_share"].to_list() == pytest.approx([0.7, 0.2, 0.1])


def test_ownership_share_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        ownership_share(pl.DataFrame({"entity_address": [], "amount": [], "space_id": []}))
