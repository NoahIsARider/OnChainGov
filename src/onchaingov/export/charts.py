"""Data export utilities (Parquet/CSV) and paper-quality charts."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from onchaingov.normalizers.schemas import write_csv, write_parquet

SUPPORTED_FORMATS = ("parquet", "csv")


def export_panel(
    panel: pl.DataFrame,
    path: str | Path,
    *,
    fmt: str = "parquet",
) -> Path:
    """Export a panel to the requested format.

    Raises:
        ValueError: on an unsupported format.
    """
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"unsupported format {fmt!r}; choose from {SUPPORTED_FORMATS}")
    path = Path(path)
    if fmt == "parquet":
        return write_parquet(panel, path)
    return write_csv(panel, path)


def export_multiple(
    frames: dict[str, pl.DataFrame],
    out_dir: str | Path,
    *,
    fmt: str = "parquet",
) -> list[Path]:
    """Export multiple named frames into a directory."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, frame in frames.items():
        suffix = ".csv" if fmt == "csv" else ".parquet"
        written.append(export_panel(frame, out_dir / f"{name}{suffix}", fmt=fmt))
    return written


def trend_chart(
    df: pl.DataFrame,
    *,
    time_col: str = "date",
    value_col: str = "voter_count",
    out_path: str | Path,
    title: str | None = None,
    group_col: str | None = None,
    figsize: tuple[float, float] = (8, 4),
) -> Path:
    """Create a line chart of a time series and save it.

    Uses matplotlib; requires ``group_col`` for multiple lines.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.figure(figsize=figsize)
    if group_col and group_col in df.columns:
        for group in df[group_col].unique().to_list():
            sub = df.filter(pl.col(group_col) == group).sort(time_col)
            plt.plot(sub[time_col], sub[value_col], label=str(group))
        plt.legend()
    else:
        sub = df.sort(time_col)
        plt.plot(sub[time_col], sub[value_col])
    plt.title(title or f"{value_col} over time")
    plt.xlabel(time_col)
    plt.ylabel(value_col)
    plt.grid(alpha=0.3)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    return out


def event_study_chart(
    relative_periods: list[int],
    coefficients: list[float],
    std_errors: list[float],
    out_path: str | Path,
    *,
    title: str = "Event study estimates",
) -> Path:
    """Plot event study point estimates with confidence intervals."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    r = np.asarray(relative_periods)
    c = np.asarray(coefficients)
    se = np.asarray(std_errors)
    fig, ax = plt.subplots(figsize=(8, 5))
    fig.tight_layout()
    ax.errorbar(r, c, yerr=1.96 * se, fmt="o", capsize=3)
    ax.axhline(0, color="black", lw=0.8, ls="--")
    ax.axvline(-1, color="grey", lw=0.8, ls=":")
    ax.set_title(title)
    ax.set_xlabel("Relative period")
    ax.set_ylabel("Estimate")
    ax.grid(alpha=0.3)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    return out


def placebo_distribution_chart(
    estimates: list[float],
    out_path: str | Path,
    *,
    true_att: float | None = None,
    title: str = "Placebo distribution",
) -> Path:
    """Histogram of placebo estimates with the true ATT marked."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.figure(figsize=(7, 4))
    plt.hist(estimates, bins=min(30, max(10, len(estimates))), alpha=0.7)
    if true_att is not None:
        plt.axvline(true_att, color="red", lw=1.5, label=f"true ATT = {true_att:.4f}")
        plt.legend()
    plt.title(title)
    plt.xlabel("Pseudo-ATT")
    plt.ylabel("Frequency")
    plt.grid(alpha=0.3)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    return out
