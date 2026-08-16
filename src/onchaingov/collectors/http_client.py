"""HTTP client helpers for GraphQL and REST data sources."""

from __future__ import annotations

from typing import Any

import httpx

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
DEFAULT_HEADERS = {"User-Agent": "OnChainGov/0.1"}


def post_json(url: str, json: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """POST a JSON payload and return parsed response.

    Raises:
        httpx.HTTPStatusError: on non-2xx response.
    """
    merged = {**DEFAULT_HEADERS, **(headers or {})}
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        resp = client.post(url, json=json, headers=merged)
        resp.raise_for_status()
        return resp.json()


def get_json(url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """GET a URL and return parsed response."""
    merged = {**DEFAULT_HEADERS, **(headers or {})}
    with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
        resp = client.get(url, params=params, headers=merged)
        resp.raise_for_status()
        return resp.json()
