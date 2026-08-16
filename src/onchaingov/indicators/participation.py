"""Governance participation metrics.

Metrics computed from vote/proposal event data:
- voter_count: number of distinct voters per group
- proposal_count: number of proposals per group
- participation_rate: share of eligible voters that voted
- voting_intensity: votes per voter
- avg_votes_per_proposal: mean votes received by proposals
"""

from __future__ import annotations

import polars as pl

PARTICIPATION_COLUMNS = [
    "voter_count",
    "proposal_count",
    "participation_rate",
    "voting_intensity",
    "avg_votes_per_proposal",
]


def participation_metrics(
    votes: pl.DataFrame,
    proposals: pl.DataFrame | None = None,
    *,
    eligible_voters: int | None = None,
    group_col: str = "space_id",
) -> pl.DataFrame:
    """Compute governance participation metrics grouped by ``group_col``.

    Args:
        votes: Event frame with columns ``entity_address`` (voter), ``timestamp``,
            and a group column. Votes may be aggregated per group.
        proposals: Optional proposal frame for proposal counts and votes-per-proposal.
        eligible_voters: Total eligible voters (used for participation_rate).
        group_col: Column name used to group results.

    Returns:
        A DataFrame with one row per group containing participation metrics.
    """
    if votes.is_empty():
        raise ValueError("votes frame is empty")

    has_group = group_col in votes.columns
    agg_exprs = [
        pl.col("entity_address").n_unique().alias("voter_count"),
        pl.col("entity_id").count().alias("vote_count"),
    ]

    if has_group:
        grouped = votes.group_by(group_col).agg(agg_exprs)
    else:
        grouped = votes.select(agg_exprs).with_columns(pl.lit("all").alias(group_col))

    n_proposals = 0
    if proposals is not None and not proposals.is_empty():
        n_proposals = proposals.height
    grouped = grouped.with_columns(
        pl.lit(n_proposals).alias("proposal_count"),
    )

    if eligible_voters and eligible_voters > 0:
        grouped = grouped.with_columns(
            (pl.col("voter_count") / eligible_voters).alias("participation_rate")
        )
    else:
        grouped = grouped.with_columns(pl.lit(None).cast(pl.Float64).alias("participation_rate"))

    grouped = grouped.with_columns(
        (pl.col("vote_count") / pl.col("voter_count")).alias("voting_intensity"),
    )

    if proposals is not None and not proposals.is_empty() and n_proposals > 0:
        grouped = grouped.with_columns(
            (pl.col("vote_count") / n_proposals).alias("avg_votes_per_proposal")
        )
    else:
        grouped = grouped.with_columns(
            pl.lit(None).cast(pl.Float64).alias("avg_votes_per_proposal")
        )

    cols = [group_col] + ["vote_count"] + PARTICIPATION_COLUMNS
    return grouped.select(cols).sort(group_col)


def voter_daily_counts(votes: pl.DataFrame, *, group_col: str = "space_id") -> pl.DataFrame:
    """Count distinct voters per day for time-series analysis."""
    expr = [
        pl.col("timestamp").dt.date().alias("date"),
        pl.col("entity_address").n_unique().alias("voter_count"),
    ]
    if group_col in votes.columns:
        return votes.group_by([group_col, "date"]).agg(expr[1]).select([group_col, "date", "voter_count"])
    return votes.with_columns(pl.col("timestamp").dt.date().alias("date")).group_by("date").agg(
        pl.col("entity_address").n_unique().alias("voter_count")
    )
