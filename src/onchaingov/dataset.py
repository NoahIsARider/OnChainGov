"""Dataset assembly and publishing (v3).

Assembles the outputs of the full research pipeline (raw events, indicators,
panels, reproductions) into a self-contained, citable "published dataset"
directory with a JSON metadata manifest and optional CSV exports. This is the
deliverable for the "publish a research-ready dataset" roadmap item.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from onchaingov import __version__

SUBDIRS = ("raw", "indicators", "panels", "reproductions")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _git_commit(repo: Path) -> str | None:
    try:
        out = repo / ".git"
        if out.exists():
            import subprocess

            return subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                text=True,
            ).strip()
    except (subprocess.CalledProcessError, OSError):  # pragma: no cover
        pass
    return None


def _checksum(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def summarize_data_dir(data_dir: str | Path) -> dict[str, Any]:
    """Summarize what pipeline artifacts exist under ``data_dir``.

    Returns a mapping of subdirectory -> list of files with sizes and row
    counts (for parquet frames). Nested subdirectories are included.
    """
    data_dir = Path(data_dir)
    summary: dict[str, Any] = {}
    for sub in SUBDIRS:
        d = data_dir / sub
        files: list[dict[str, Any]] = []
        if d.exists():
            for f in sorted(d.rglob("*.parquet")) + sorted(d.rglob("*.csv")):
                entry: dict[str, Any] = {
                    "name": f.relative_to(d).as_posix(),
                    "bytes": f.stat().st_size,
                    "format": f.suffix.lstrip("."),
                }
                if f.suffix == ".parquet":
                    try:
                        entry["rows"] = pl.read_parquet(f).height
                    except (OSError, ValueError, pl.exceptions.PolarsError):
                        entry["rows"] = None
                files.append(entry)
        summary[sub] = files
    return summary


def build_manifest(
    data_dir: str | Path,
    *,
    title: str | None = None,
    authors: list[str] | None = None,
    version: str = __version__,
    description: str | None = None,
) -> dict[str, Any]:
    """Build the dataset metadata manifest dict."""
    data_dir = Path(data_dir)
    return {
        "name": title or "onchaingov-panel-dataset",
        "description": description
        or "Research-ready DAO governance panel dataset assembled by OnChainGov.",
        "version": version,
        "generated_at": _iso_now(),
        "toolchain": {
            "name": "onchaingov",
            "version": __version__,
            "commit": _git_commit(data_dir.parent),
            "schema_version": 1,
        },
        "contents": summarize_data_dir(data_dir),
    }


def publish_dataset(
    data_dir: str | Path,
    out_dir: str | Path,
    *,
    title: str | None = None,
    authors: list[str] | None = None,
    version: str = __version__,
    description: str | None = None,
    with_csv: bool = False,
) -> dict[str, Any]:
    """Assemble a published dataset from pipeline outputs.

    Copies all artifacts (Parquet, optionally CSV) into ``out_dir`` and
    writes ``dataset.json`` plus a ``README.md``. Returns the manifest.
    """
    data_dir = Path(data_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    version = version or __version__

    for sub in SUBDIRS:
        src = data_dir / sub
        dst = out_dir / sub
        if not src.exists():
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for f in sorted(src.rglob("*.parquet")):
            rel = f.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            pl.read_parquet(f).write_parquet(target)
            if with_csv:
                pl.read_parquet(f).write_csv(target.with_suffix(".csv"))

    manifest = build_manifest(
        data_dir,
        title=title,
        authors=authors,
        version=version,
        description=description,
    )
    manifest["files"] = {
        sub: [{"name": f.relative_to(out_dir / sub).as_posix(),
               "sha256": _checksum(f)}
              for f in sorted((out_dir / sub).rglob("*.parquet"))]
        for sub in SUBDIRS if (out_dir / sub).exists()
    }
    (out_dir / "dataset.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "README.md").write_text(_readme_text(manifest), encoding="utf-8")
    return manifest


def _readme_text(manifest: dict[str, Any]) -> str:
    lines = [
        f"# {manifest['name']}",
        "",
        manifest["description"],
        "",
        "## Metadata",
        "",
        f"- Version: {manifest['version']}",
        f"- Generated: {manifest['generated_at']}",
        (
            f"- Toolchain: {manifest['toolchain']['name']} "
            f"{manifest['toolchain']['version']} (commit {manifest['toolchain']['commit'] or 'n/a'})"
        ),
        "",
        "## Contents",
        "",
    ]
    for sub, files in manifest["contents"].items():
        if not files:
            continue
        lines.append(f"### {sub}")
        lines.append("")
        lines.append("| file | rows | bytes |")
        lines.append("|------|------|-------|")
        for f in files:
            rows = f.get("rows") if f.get("rows") is not None else "-"
            lines.append(f"| {f['name']} | {rows} | {f['bytes']} |")
        lines.append("")
    lines.extend(
        [
            "## Reproducibility",
            "",
            (
                "This dataset was produced by OnChainGov "
                "(https://github.com/NoahIsARider/OnChainGov). Re-run the pipeline with:"
            ),
            "",
            "```bash",
            "onchaingov collect ...   # collect raw events",
            "onchaingov indicators --data-dir data/raw --out data/indicators",
            "onchaingov panel --data-dir data/raw --out data/panels",
            "onchaingov did --panel data/panels/panel.parquet --outcome outcome_*",
            "onchaingov reproduce jom2025 --demo --out data/reproductions/jom2025",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"
