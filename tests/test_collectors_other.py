"""Tests for Tally, EVM RPC, and Steemit collectors."""

import pytest

from onchaingov.collectors.steemit import SteemitCollector
from onchaingov.collectors.tally import TallyCollector


class _FakeRPC:
    def __init__(self, response):
        self.response = response

    def __call__(self, url, json, headers=None):
        return self.response


def test_tally_collect_proposals(monkeypatch):
    resp = {
        "data": {
            "governances": [
                {
                    "id": "g1",
                    "name": "Governance",
                    "slug": "slug1",
                    "organization": {"id": "o1", "name": "Org"},
                    "proposals": {
                        "nodes": [
                            {
                                "id": "proposal1",
                                "title": "T1",
                                "description": "",
                                "status": "closed",
                                "startTime": {"timestamp": "1704067200"},
                                "endTime": {"timestamp": "1704153600"},
                                "createdTime": {"timestamp": "1704000000"},
                                "proposer": {"address": "0xabc"},
                                "votes": {"total": 10},
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    },
                }
            ]
        }
    }
    fake = _FakeRPC(resp)
    monkeypatch.setattr("onchaingov.collectors.tally.post_json", fake)
    collector = TallyCollector(api_key="test-key")
    events = collector.run("slug1")
    assert len(events) == 1
    assert events[0].source == "tally"
    assert events[0].event_type == "proposal"
    assert events[0].entity_id == "proposal1"
    assert events[0].payload["votes"] == 10


def test_steemit_collect_posts(monkeypatch):
    posts = [
        {
            "id": 123,
            "author": "alice",
            "permlink": "post-1",
            "title": "Hello",
            "category": "life",
            "created": "2024-01-01T12:00:00",
            "net_votes": 5,
            "total_payout_value": "10.000 SBD",
            "curator_payout_value": "3.000 SBD",
            "pending_payout_value": "0.000 SBD",
            "active_votes": [{"voter": "bob", "weight": 10000, "rshares": "12345", "time": "2024-01-01T13:00:00"}],
        }
    ]
    resp = {"jsonrpc": "2.0", "result": posts, "id": 1}
    fake = _FakeRPC(resp)
    monkeypatch.setattr("onchaingov.collectors.steemit.post_json", fake)
    collector = SteemitCollector()
    events = collector.run(limit=1, collect_votes=True)
    assert len(events) == 2
    assert events[0].event_type == "post"
    assert events[0].entity_address == "alice"
    assert events[0].payload["total_payout_value"] == "10.000 SBD"
    assert events[1].event_type == "vote"
    assert events[1].payload["voter"] == "bob"


def test_steemit_parse_payout():
    from onchaingov.indicators.token_incentive import _parse_payout

    assert _parse_payout("12.345 SBD") == 12.345
    assert _parse_payout(5.0) == 5.0
    assert _parse_payout(None) == 0.0
    assert _parse_payout("garbage") == 0.0


def test_evm_collector_requires_config():
    from onchaingov.collectors import EVMRPCCollector

    collector = EVMRPCCollector()
    with pytest.raises(ValueError, match="rpc_url"):
        collector.run(from_block=1)
    collector.rpc_url = "http://localhost:8545"
    with pytest.raises(ValueError, match="contract_address"):
        collector.run(from_block=1)
