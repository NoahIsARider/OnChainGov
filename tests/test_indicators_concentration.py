"""Tests for participation and concentration indicators."""

import polars as pl
import pytest

from onchaingov.indicators import (
    concentration_metrics,
    gini,
    herfindahl,
    normalized_entropy,
    participation_metrics,
    top_share,
)
from tests.conftest import make_proposal_frame, make_vote_frame


def test_participation_metrics_counts():
    votes = make_vote_frame()
    proposals = make_proposal_frame()
    df = participation_metrics(votes, proposals, group_col="space_id")
    assert df["space_id"].to_list() == ["space_a", "space_b"]
    row_a = df.filter(pl.col("space_id") == "space_a")
    assert row_a["proposal_count"][0] == 2
    # voters in space_a: 0xaaa, 0xccc (2 distinct)
    assert row_a["voter_count"][0] == 2
    assert row_a["vote_count"][0] == 3


def test_participation_metrics_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        participation_metrics(pl.DataFrame({"a": []}))


def test_herfindahl_equal():
    assert herfindahl([1.0, 1.0, 1.0, 1.0]) == pytest.approx(0.25)


def test_herfindahl_monopoly():
    assert herfindahl([10.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_herfindahl_empty():
    assert herfindahl([]) != herfindahl([])  # nan


def test_gini_equal():
    assert gini([1.0, 1.0, 1.0]) == pytest.approx(0.0)


def test_gini_concentrated():
    g = gini([0.0, 0.0, 10.0])
    assert g == pytest.approx(2 / 3)


def test_top_share():
    shares = [100.0, 1.0, 1.0, 1.0]
    assert top_share(shares, 0.25) == pytest.approx(100 / 103)


def test_normalized_entropy_bounds():
    e = normalized_entropy([1.0, 1.0, 1.0, 1.0])
    assert e == pytest.approx(1.0)
    e2 = normalized_entropy([10.0, 0.0, 0.0])
    assert e2 == pytest.approx(0.0)


def test_concentration_metrics_full():
    m = concentration_metrics([10.0, 2.0, 1.0, 1.0])
    assert "herfindahl" in m
    assert m["gini"] > 0
    assert 0 <= m["top_10_share"] <= 1
