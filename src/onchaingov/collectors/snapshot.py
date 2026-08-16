"""Snapshot (hub.snapshot.org) GraphQL collector."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from onchaingov.collectors.base import Collector, RawEvent
from onchaingov.collectors.http_client import post_json

SNAPSHOT_GRAPHQL_URL = "https://hub.snapshot.org/graphql"
PAGE_SIZE = 1000

PROPOSALS_QUERY = """
query Proposals($space: String!, $first: Int!, $skip: Int!, $created_gte: Int) {
  proposals(
    first: $first, skip: $skip,
    where: {space: $space, created_gte: $created_gte},
    orderBy: "created", orderDirection: asc
  ) {
    id
    title
    body
    choices
    start
    end
    snapshot
    state
    author
    created
    type
    scores
    scores_total
    votes
    quorum
    space { id name symbol }
  }
}
"""

VOTES_QUERY = """
query Votes($proposal: String!, $first: Int!, $skip: Int!) {
  votes(
    first: $first, skip: $skip,
    where: {proposal: $proposal},
    orderBy: "created", orderDirection: asc
  ) {
    id
    voter
    created
    choice
    vp
    vp_by_strategy
    proposal { id }
  }
}
"""


class SnapshotCollector(Collector):
    """Collect proposals and votes from a Snapshot space."""

    source_name = "snapshot"

    def __init__(
        self,
        out_dir: str | Path | None = None,
        *,
        graphql_url: str = SNAPSHOT_GRAPHQL_URL,
    ) -> None:
        super().__init__(out_dir)
        self.graphql_url = graphql_url

    def run(
        self,
        space: str,
        since: str | datetime | int | None = None,
        *,
        collect_votes: bool = True,
    ) -> list[RawEvent]:
        """Collect proposals (and optionally their votes) for a space.

        Args:
            space: Snapshot space id, e.g. "uniswap".
            since: Only collect proposals created after this date.
                Accepts ISO date string, datetime, or unix timestamp.
            collect_votes: Also fetch votes for each proposal.

        Returns:
            List of RawEvent (event_type in {"proposal", "vote"}).
        """
        created_gte = self._since_to_ts(since)
        proposals = self._fetch_all_proposals(space, created_gte)
        events: list[RawEvent] = []
        for p in proposals:
            events.append(self._proposal_event(p))
            if collect_votes:
                events.extend(self._fetch_votes_for_proposal(p["id"]))
        return events

    def _fetch_all_proposals(self, space: str, created_gte: int | None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        skip = 0
        while True:
            variables: dict[str, Any] = {"space": space, "first": PAGE_SIZE, "skip": skip}
            if created_gte is not None:
                variables["created_gte"] = created_gte
            body = {
                "query": PROPOSALS_QUERY,
                "variables": variables,
            }
            data = post_json(self.graphql_url, body)
            batch = (data.get("data") or {}).get("proposals") or []
            out.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            skip += PAGE_SIZE
        return out

    def _fetch_votes_for_proposal(self, proposal_id: str) -> list[RawEvent]:
        events: list[RawEvent] = []
        skip = 0
        while True:
            variables = {"proposal": proposal_id, "first": PAGE_SIZE, "skip": skip}
            data = post_json(
                self.graphql_url,
                {"query": VOTES_QUERY, "variables": variables},
            )
            batch = (data.get("data") or {}).get("votes") or []
            for v in batch:
                events.append(
                    RawEvent(
                        source=self.source_name,
                        event_type="vote",
                        entity_id=v["id"],
                        entity_address=v.get("voter"),
                        timestamp=self._ts(v.get("created")),
                        payload={
                            "proposal_id": proposal_id,
                            "choice": v.get("choice"),
                            "vp": v.get("vp"),
                            "vp_by_strategy": v.get("vp_by_strategy"),
                        },
                        raw=v,
                    )
                )
            if len(batch) < PAGE_SIZE:
                break
            skip += PAGE_SIZE
        return events

    def _proposal_event(self, p: dict[str, Any]) -> RawEvent:
        space = p.get("space") or {}
        return RawEvent(
            source=self.source_name,
            event_type="proposal",
            entity_id=p["id"],
            entity_address=p.get("author"),
            timestamp=self._ts(p.get("created")),
            payload={
                "space_id": space.get("id"),
                "space_name": space.get("name"),
                "title": p.get("title"),
                "choices": p.get("choices"),
                "start": p.get("start"),
                "end": p.get("end"),
                "state": p.get("state"),
                "type": p.get("type"),
                "scores_total": p.get("scores_total"),
                "votes": p.get("votes"),
                "quorum": p.get("quorum"),
            },
            raw=p,
        )

    @staticmethod
    def _ts(value: Any) -> datetime:
        """Convert unix timestamp to UTC datetime (naive-safe)."""
        if value is None:
            return datetime(1970, 1, 1, tzinfo=timezone.utc).replace(tzinfo=None)
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _since_to_ts(since: str | datetime | int | None) -> int | None:
        if since is None:
            return None
        if isinstance(since, int):
            return since
        if isinstance(since, datetime):
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            return int(since.timestamp())
        # ISO string
        dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
