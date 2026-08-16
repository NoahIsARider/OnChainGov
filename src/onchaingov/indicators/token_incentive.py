"""Token incentive metrics.

Implements the four incentive dimensions used in the Steemit/JOM research
lineage:

- creation: reward for producing content (e.g. author payout per post).
- curation: reward for curating/upvoting content (e.g. curator payout).
- novelty: freshness/uniqueness of contributed content (time since last
  activity, first-time contributor flag, content distinctiveness).
- ownership_share: a user's share of total token holdings / voting power.

The metrics are pure functions over polars DataFrames and follow the
convention of taking a unit id (user) and returning per-unit values.
"""

from __future__ import annotations

import polars as pl

# Unified column names used by the metric helpers
POST_AUTHOR_COL = "author"
POST_PAYOUT_COL = "total_payout_value"
POST_ID_COL = "entity_id"
POST_TIME_COL = "timestamp"
VOTE_VOTER_COL = "voter"
VOTE_WEIGHT_COL = "weight"
HOLDING_OWNER_COL = "entity_address"
HOLDING_AMOUNT_COL = "amount"


def _parse_payout(value) -> float:
    """Parse a Steemit-style payout string like '12.345 SBD' into a float."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).split()[0])
    except (ValueError, IndexError):
        return 0.0


def creation_metric(posts: pl.DataFrame, *, unit_col: str = POST_AUTHOR_COL) -> pl.DataFrame:
    """Compute per-author content creation reward.

    Returns a frame with columns ``unit_col`` and ``creation`` (cumulative
    author payout) and ``post_count``.
    """
    if posts.is_empty():
        return pl.DataFrame(
            {unit_col: [], "creation": [], "post_count": []},
            schema={unit_col: pl.String, "creation": pl.Float64, "post_count": pl.Int64},
        )
    df = posts.with_columns(pl.col(POST_PAYOUT_COL).map_elements(_parse_payout, return_dtype=pl.Float64))
    return (
        df.group_by(unit_col)
        .agg(
            pl.col(POST_PAYOUT_COL).sum().alias("creation"),
            pl.col(POST_ID_COL).count().alias("post_count"),
        )
    )


def curation_metric(votes: pl.DataFrame, *, unit_col: str = VOTE_VOTER_COL) -> pl.DataFrame:
    """Compute per-voter curation activity.

    Uses the vote weight as a proxy for curation reward; returns ``curation``
    (sum of weights) and ``vote_count``.
    """
    if votes.is_empty():
        return pl.DataFrame(
            {unit_col: [], "curation": [], "vote_count": []},
            schema={unit_col: pl.String, "curation": pl.Float64, "vote_count": pl.Int64},
        )
    df = votes.with_columns(pl.col(VOTE_WEIGHT_COL).cast(pl.Float64, strict=False).fill_null(0.0))
    return (
        df.group_by(unit_col)
        .agg(
            pl.col(VOTE_WEIGHT_COL).sum().alias("curation"),
            pl.col(VOTE_WEIGHT_COL).count().alias("vote_count"),
        )
    )


def novelty_metric(
    events: pl.DataFrame,
    *,
    unit_col: str = "entity_address",
    time_col: str = POST_TIME_COL,
) -> pl.DataFrame:
    """Compute content novelty per unit.

    Novelty is defined as the average gap (in days) between consecutive
    contributions by the same unit; a smaller gap implies more frequent,
    fresher contributions. Also returns ``first_time`` flag (1 if the unit
    has a single event) and ``activity_days``.
    """
    if events.is_empty():
        return pl.DataFrame(
            {unit_col: [], "novelty": [], "first_time": [], "activity_days": []},
            schema={
                unit_col: pl.String,
                "novelty": pl.Float64,
                "first_time": pl.Int8,
                "activity_days": pl.Float64,
            },
        )
    df = events.sort([unit_col, time_col])
    df = df.with_columns(pl.col(time_col).dt.date().alias("date"))
    grouped = df.group_by([unit_col, "date"]).agg(pl.col(time_col).max().alias("ts"))
    # gaps between consecutive activity dates (in days)
    grouped = grouped.sort([unit_col, "date"]).with_columns(
        (pl.col("date").diff(n=1).dt.total_days()).over(unit_col).alias("gap_days")
    )
    stats = grouped.group_by(unit_col).agg(
        pl.col("gap_days").mean().alias("avg_gap_days"),
        pl.col("date").n_unique().alias("activity_days"),
    )
    stats = stats.with_columns(
        pl.when(pl.col("activity_days") <= 1)
        .then(pl.lit(1, dtype=pl.Int8))
        .otherwise(pl.lit(0, dtype=pl.Int8))
        .alias("first_time"),
        pl.col("avg_gap_days").fill_null(0.0).cast(pl.Float64).alias("novelty"),
    )
    return stats.select(unit_col, "novelty", "first_time", "activity_days")


def ownership_share(
    holdings: pl.DataFrame,
    *,
    owner_col: str = HOLDING_OWNER_COL,
    amount_col: str = HOLDING_AMOUNT_COL,
    group_col: str = "space_id",
) -> pl.DataFrame:
    """Compute each holder's ownership share of the total supply.

    Returns per-owner share within each group: ``ownership_share`` in [0, 1].
    """
    if holdings.is_empty():
        raise ValueError("holdings frame is empty")
    df = holdings.with_columns(pl.col(amount_col).cast(pl.Float64, strict=False).fill_null(0.0))
    total = df.group_by(group_col).agg(pl.col(amount_col).sum().alias("total"))
    merged = df.join(total, on=group_col, how="left")
    return merged.with_columns(
        pl.when(pl.col("total") == 0)
        .then(pl.lit(0.0))
        .otherwise(pl.col(amount_col) / pl.col("total"))
        .alias("ownership_share")
    ).select(owner_col, group_col, "ownership_share")


def incentive_profile(
    creation: pl.DataFrame,
    curation: pl.DataFrame,
    novelty: pl.DataFrame,
    *,
    unit_col: str = "unit",
) -> pl.DataFrame:
    """Combine the incentive dimensions into a single per-unit profile.

    Joins creation, curation, and novelty frames on ``unit_col``.
    """
    frames = []
    rename_map = {
        "creation": ("creation", creation),
        "curation": ("curation", curation),
        "novelty": ("novelty", novelty),
    }
    base_col = None
    for name, (_, frame) in rename_map.items():
        if frame.is_empty():
            continue
        cols = frame.columns
        if base_col is None:
            # find the identity column
            for c in cols:
                if c in (unit_col, "author", "voter", "entity_address"):
                    base_col = c
                    break
            if base_col is None:
                base_col = cols[0]
        sub = frame.rename({base_col: unit_col}).select([unit_col, name])
        frames.append(sub)

    if not frames:
        return pl.DataFrame({unit_col: []}, schema={unit_col: pl.String})
    out = frames[0]
    for f in frames[1:]:
        out = out.join(f, on=unit_col, how="full", coalesce=True)
    return out
