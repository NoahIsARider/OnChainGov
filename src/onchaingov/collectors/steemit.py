"""Steemit blockchain collector for content creation and curation activity.

Uses the Steemit condenser JSON-RPC API to pull post creation and vote
(curation) activity. This is the data source behind the JOM 2025 Steemit
reproduction (governance token vs. tradeable token incentive effects).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from onchaingov.collectors.base import Collector, RawEvent
from onchaingov.collectors.http_client import post_json

STEEMIT_RPC_URL = "https://api.steemit.com"


class SteemitCollector(Collector):
    """Collect posts and votes from the Steemit blockchain via condenser API."""

    source_name = "steemit"

    def __init__(
        self,
        out_dir: str | Path | None = None,
        *,
        rpc_url: str = STEEMIT_RPC_URL,
    ) -> None:
        super().__init__(out_dir)
        self.rpc_url = rpc_url

    def _call(self, method: str, params: list[Any]) -> Any:
        body = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
        data = post_json(self.rpc_url, body)
        if "error" in data:
            raise RuntimeError(f"Steemit RPC error: {data['error']}")
        return data.get("result")

    def run(
        self,
        *,
        tag: str = "life",
        limit: int = 100,
        collect_votes: bool = False,
    ) -> list[RawEvent]:
        """Collect the latest posts for a tag.

        Args:
            tag: Steemit content tag to scan.
            limit: Maximum number of posts to fetch (1-100).
            collect_votes: Also fetch the active votes for each post.

        Returns:
            List of RawEvent with event_type in {"post", "vote"}.
        """
        posts = self._call("condenser.get_discussions_by_created", [{"tag": tag, "limit": limit}])
        if not posts:
            return []
        events: list[RawEvent] = []
        for p in posts:
            events.append(self._post_event(p))
            if collect_votes and p.get("active_votes"):
                for v in p["active_votes"]:
                    events.append(
                        RawEvent(
                            source=self.source_name,
                            event_type="vote",
                            entity_id=f"{p['id']}:{v.get('voter', '')}",
                            entity_address=None,
                            timestamp=self._parse_time(v.get("time")),
                            payload={
                                "post_id": p.get("id"),
                                "voter": v.get("voter"),
                                "weight": v.get("weight"),
                                "rshares": v.get("rshares"),
                            },
                            raw=v,
                        )
                    )
        return events

    def _post_event(self, p: dict[str, Any]) -> RawEvent:
        author = p.get("author", "")
        return RawEvent(
            source=self.source_name,
            event_type="post",
            entity_id=str(p.get("id", "")),
            entity_address=author,
            timestamp=self._parse_time(p.get("created")),
            payload={
                "author": author,
                "permlink": p.get("permlink"),
                "title": p.get("title"),
                "category": p.get("category"),
                "net_votes": p.get("net_votes"),
                "total_payout_value": p.get("total_payout_value"),
                "curator_payout_value": p.get("curator_payout_value"),
                "pending_payout_value": p.get("pending_payout_value"),
            },
            raw=p,
        )

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if not value:
            return datetime(1970, 1, 1)
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            return datetime(1970, 1, 1)
