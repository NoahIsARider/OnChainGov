"""Tests for the Snapshot collector (mock transport)."""

import polars as pl
import pytest

from onchaingov.collectors import RawEvent, SnapshotCollector


class _FakeClient:
    """Replaces post_json for tests; serves proposals then votes."""

    def __init__(self, proposals, votes_per_proposal):
        self.proposals = proposals
        self.votes = votes_per_proposal
        self.calls = 0

    def __call__(self, url, json, headers=None):
        query = json["query"]
        if "query Proposals" in query:
            return {"data": {"proposals": self.proposals}}
        if "query Votes" in query:
            proposal = json["variables"]["proposal"]
            return {"data": {"votes": self.votes.get(proposal, [])}}
        return {"data": {}}


def test_snapshot_run_produces_events(monkeypatch):
    proposals = [
        {
            "id": "p1",
            "title": "Proposal 1",
            "body": "",
            "choices": ["For", "Against"],
            "start": 1704067200,
            "end": 1704153600,
            "snapshot": 0,
            "state": "closed",
            "author": "0xabc",
            "created": 1704000000,
            "type": "single-choice",
            "scores_total": 100.0,
            "votes": 2,
            "quorum": 50.0,
            "space": {"id": "myspace", "name": "My Space", "symbol": "MSP"},
        }
    ]
    votes = {
        "p1": [
            {"id": "pv1", "voter": "0xaaa", "created": 1704068000, "choice": 1, "vp": 10.0, "vp_by_strategy": [10.0], "proposal": {"id": "p1"}},
            {"id": "pv2", "voter": "0xbbb", "created": 1704069000, "choice": 2, "vp": 5.0, "vp_by_strategy": [5.0], "proposal": {"id": "p1"}},
        ]
    }
    fake = _FakeClient(proposals, votes)
    monkeypatch.setattr("onchaingov.collectors.snapshot.post_json", fake)

    collector = SnapshotCollector()
    events = collector.run("myspace", since="2024-01-01")
    assert len(events) == 3
    types = {e.event_type for e in events}
    assert types == {"proposal", "vote"}
    votes_found = [e for e in events if e.event_type == "vote"]
    assert len(votes_found) == 2
    assert votes_found[0].entity_address == "0xaaa"
    assert votes_found[0].payload["vp"] == 10.0


def test_snapshot_since_ts():
    collector = SnapshotCollector()
    ts = collector._since_to_ts("2024-01-01")
    assert ts == 1704067200


def test_snapshot_since_datetime():
    from datetime import datetime, timezone

    collector = SnapshotCollector()
    ts = collector._since_to_ts(datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert ts == 1704067200


def test_snapshot_save_writes_parquet(tmp_path):
    collector = SnapshotCollector(tmp_path)
    events = [
        RawEvent(
            source="snapshot",
            event_type="proposal",
            entity_id="p1",
            timestamp=pl.Series(["2024-01-01"]).str.to_datetime()[0],
        )
    ]
    path = collector.save(events, name="test_events")
    assert path.exists()
    df = pl.read_parquet(path)
    assert df.height == 1


def test_snapshot_collector_missing_out_dir():
    collector = SnapshotCollector()
    with pytest.raises(ValueError, match="out_dir"):
        collector.save([])
