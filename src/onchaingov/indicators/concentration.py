"""Voting power concentration metrics.

Standard measures of concentration commonly used in governance research:
- herfindahl: Herfindahl-Hirschman Index of vote shares (sum of squared shares)
- gini: Gini coefficient of vote shares
- top_share(0.1): share of total voting power held by the top 10%
- entropy: Shannon entropy of the vote-share distribution (normalized)
"""

from __future__ import annotations

import numpy as np
import polars as pl


def herfindahl(shares: pl.Series | list[float]) -> float:
    """Herfindahl-Hirschman Index from a vector of shares.

    HHI = sum(s_i^2). Ranges from 1/N (equal) to 1 (monopoly).
    """
    shares = _to_np(shares)
    if shares.size == 0:
        return float("nan")
    total = shares.sum()
    if total <= 0:
        return float("nan")
    p = shares / total
    return float((p**2).sum())


def effective_share_count(shares: pl.Series | list[float]) -> float:
    """Inverse HHI: the equivalent number of equal-sized voters."""
    h = herfindahl(shares)
    if h is None or np.isnan(h) or h == 0:
        return float("nan")
    return 1.0 / h


def gini(shares: pl.Series | list[float]) -> float:
    """Gini coefficient computed from a vector of voting-power values.

    Values in [0, 1]; 0 = perfect equality, 1 = maximal concentration.
    """
    x = _to_np(shares)
    if x.size == 0:
        return float("nan")
    x = x[x >= 0]
    if x.size == 0 or x.sum() <= 0:
        return float("nan")
    x = np.sort(x)
    n = x.size
    total = x.sum()
    cum = np.cumsum(x, dtype=np.float64)
    return float((n + 1 - 2 * np.sum(cum) / total) / n)


def top_share(shares: pl.Series | list[float], q: float = 0.1) -> float:
    """Share of total voting power held by the top ``q`` fraction of voters."""
    x = _to_np(shares)
    if x.size == 0 or x.sum() <= 0:
        return float("nan")
    k = max(1, int(np.ceil(x.size * q)))
    top = np.sort(x)[::-1][:k]
    return float(top.sum() / x.sum())


def normalized_entropy(shares: pl.Series | list[float]) -> float:
    """Shannon entropy normalized to [0, 1] by log(N)."""
    x = _to_np(shares)
    if x.size == 0:
        return float("nan")
    x = x[x > 0]
    if x.size == 0 or x.sum() <= 0:
        return float("nan")
    if x.size == 1:
        return 0.0
    p = x / x.sum()
    h = -np.sum(p * np.log(p))
    return float(h / np.log(x.size))


def concentration_metrics(shares: pl.Series | list[float]) -> dict[str, float]:
    """Compute the full set of concentration metrics for a vote-share vector."""
    return {
        "herfindahl": herfindahl(shares),
        "gini": gini(shares),
        "effective_share_count": effective_share_count(shares),
        "top_10_share": top_share(shares, 0.1),
        "top_1_share": top_share(shares, 0.01),
        "normalized_entropy": normalized_entropy(shares),
    }


def concentration_by_group(
    df: pl.DataFrame,
    *,
    value_col: str = "vp",
    voter_col: str = "entity_address",
    group_col: str = "space_id",
) -> pl.DataFrame:
    """Compute concentration metrics per group from a vote frame.

    Args:
        df: Vote frame with voter and voting-power columns.
        value_col: Column holding per-vote voting power (vp).
        voter_col: Column identifying the voter.
        group_col: Grouping column (e.g. space_id or period).

    Returns:
        DataFrame with ``group_col`` plus all concentration metrics.
    """
    if df.is_empty():
        raise ValueError("vote frame is empty")
    if not {value_col, voter_col, group_col}.issubset(df.columns):
        raise ValueError(
            f"frame must contain columns {value_col!r}, {voter_col!r}, {group_col!r}"
        )

    # Sum voting power per (group, voter) then compute metrics per group
    agg = df.group_by([group_col, voter_col]).agg(pl.col(value_col).sum().alias("power"))
    metric_cols = ["herfindahl", "gini", "effective_share_count", "top_10_share", "top_1_share", "normalized_entropy"]
    rows = []
    for group in agg[group_col].unique().to_list():
        sub = agg.filter(pl.col(group_col) == group)
        shares = sub["power"].to_list()
        metrics = concentration_metrics(shares)
        rows.append({group_col: group, **metrics})
    return pl.DataFrame(rows, schema={group_col: pl.String, **{c: pl.Float64 for c in metric_cols}})


def _to_np(values: pl.Series | list[float]) -> np.ndarray:
    if isinstance(values, pl.Series):
        return values.to_numpy().astype(np.float64)
    return np.asarray(values, dtype=np.float64)
