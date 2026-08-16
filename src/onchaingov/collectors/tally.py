"""Tally (tally.xyz) GraphQL collector."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from onchaingov.collectors.base import Collector, RawEvent
from onchaingov.collectors.http_client import post_json

TALLY_GRAPHQL_URL = "https://api.tally.xyz/query"
PAGE_SIZE = 500

GOVERNANCES_QUERY = """
query Governances($slug: String!, $first: Int!, $skip: Int!, $after: Int) {
  governances(slug: $slug) {
    id
    name
    slug
    organization { id name }
    proposals(first: $first, after: $after) {
      nodes {
        id
        title
        description
        status
        startTime: start {
          timestamp
        }
        endTime: end {
          timestamp
        }
        createdTime: createdAt {
          timestamp
        }
        proposer {
          address
        }
        votes {
          total
        }
      }
      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""


class TallyCollector(Collector):
    """Collect governance data from Tally.

    Note: Tally requires an API key for production access. Provide it via
    the ``api_key`` argument or the ``TALLY_API_KEY`` environment variable.
    """

    source_name = "tally"

    def __init__(
        self,
        out_dir: str | Path | None = None,
        *,
        graphql_url: str = TALLY_GRAPHQL_URL,
        api_key: str | None = None,
    ) -> None:
        super().__init__(out_dir)
        self.graphql_url = graphql_url
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        if self.api_key:
            return {"Api-key": self.api_key}
        return {}

    def run(self, slug: str) -> list[RawEvent]:
        """Collect proposals for a Tally organization slug."""
        body = {
            "query": GOVERNANCES_QUERY,
            "variables": {"slug": slug, "first": PAGE_SIZE, "skip": 0},
        }
        data = post_json(self.graphql_url, body, headers=self._headers())
        governances = ((data.get("data") or {}).get("governances")) or []
        events: list[RawEvent] = []
        for gov in governances:
            org = gov.get("organization") or {}
            for proposal in (gov.get("proposals") or {}).get("nodes") or []:
                start = proposal.get("startTime") or {}
                end = proposal.get("endTime") or {}
                created = proposal.get("createdTime") or {}
                proposer = proposal.get("proposer") or {}
                votes = proposal.get("votes") or {}
                events.append(
                    RawEvent(
                        source=self.source_name,
                        event_type="proposal",
                        entity_id=proposal["id"],
                        entity_address=proposer.get("address"),
                        timestamp=self._ts(created.get("timestamp")),
                        payload={
                            "governance_id": gov.get("id"),
                            "governance_name": gov.get("name"),
                            "organization_name": org.get("name"),
                            "title": proposal.get("title"),
                            "status": proposal.get("status"),
                            "start": start.get("timestamp"),
                            "end": end.get("timestamp"),
                            "votes": votes.get("total"),
                        },
                        raw=proposal,
                    )
                )
        return events

    @staticmethod
    def _ts(value: Any) -> datetime:
        if value is None:
            return datetime(1970, 1, 1)
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
