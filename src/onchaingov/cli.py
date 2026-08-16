"""Command-line interface for OnChainGov.

Uses argparse with subcommands matching the documented CLI surface.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from onchaingov import __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="onchaingov",
        description="On-chain governance research toolchain",
    )
    parser.add_argument("--version", action="version", version=f"onchaingov {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    # collect
    collect = sub.add_parser("collect", help="collect governance data")
    collect_sub = collect.add_subparsers(dest="source", required=True)

    sp = collect_sub.add_parser("snapshot", help="collect from Snapshot GraphQL")
    sp.add_argument("--space", required=True)
    sp.add_argument("--since", default=None, help="ISO date or unix timestamp")
    sp.add_argument("--no-votes", action="store_true", help="skip fetching votes")
    sp.add_argument("--url", default="https://hub.snapshot.org/graphql")
    sp.add_argument("--out", default="data/raw")
    sp.set_defaults(func=_cmd_collect_snapshot)

    tp = collect_sub.add_parser("tally", help="collect from Tally GraphQL")
    tp.add_argument("--slug", required=True)
    tp.add_argument("--api-key", default=None, help="Tally API key")
    tp.add_argument("--url", default="https://api.tally.xyz/query")
    tp.add_argument("--out", default="data/raw")
    tp.set_defaults(func=_cmd_collect_tally)

    ev = collect_sub.add_parser("evm", help="collect on-chain event logs")
    ev.add_argument("--rpc", required=True)
    ev.add_argument("--contract", required=True)
    ev.add_argument("--from-block", type=int, required=True)
    ev.add_argument("--to-block", type=int, default=None)
    ev.add_argument("--event", default="Transfer")
    ev.add_argument("--out", default="data/raw")
    ev.set_defaults(func=_cmd_collect_evm)

    st = collect_sub.add_parser("steemit", help="collect from Steemit")
    st.add_argument("--tag", default="life")
    st.add_argument("--limit", type=int, default=100)
    st.add_argument("--with-votes", action="store_true")
    st.add_argument("--out", default="data/raw")
    st.set_defaults(func=_cmd_collect_steemit)

    # indicators
    ind = sub.add_parser("indicators", help="compute governance indicators")
    ind.add_argument("--data-dir", default="data/raw")
    ind.add_argument("--out", default="data/indicators")
    ind.set_defaults(func=_cmd_indicators)

    # panel
    pan = sub.add_parser("panel", help="build a panel")
    pan.add_argument("--data-dir", default="data/raw")
    pan.add_argument("--unit", default="user")
    pan.add_argument("--time", default="week", choices=["day", "week", "month"])
    pan.add_argument("--out", default="data/panels")
    pan.set_defaults(func=_cmd_panel)

    # attach treatment
    at = sub.add_parser("attach-treatment", help="attach treated/post indicators to a panel")
    at.add_argument("--panel", required=True)
    at.add_argument("--treated-file", required=True, help="file of treated unit ids (one per line)")
    at.add_argument("--event-time", required=True, help="treatment start time (ISO datetime)")
    at.add_argument("--unit-id", default="unit_id")
    at.add_argument("--time-col", default="period")
    at.add_argument("--out", required=True)
    at.set_defaults(func=_cmd_attach_treatment)

    # export
    exp = sub.add_parser("export", help="export a frame")
    exp.add_argument("--input", required=True)
    exp.add_argument("--format", default="parquet", choices=["parquet", "csv"])
    exp.add_argument("--out", required=True)
    exp.set_defaults(func=_cmd_export)

    # causal
    did = sub.add_parser("did", help="difference-in-differences")
    did.add_argument("--panel", required=True)
    did.add_argument("--treatment", default="treated")
    did.add_argument("--outcome", required=True)
    did.add_argument("--post", default="post")
    did.add_argument("--unit-id", default="unit_id")
    did.add_argument("--time-col", default="period")
    did.set_defaults(func=_cmd_did)

    psm = sub.add_parser("psm-did", help="propensity-score-matched DID")
    psm.add_argument("--panel", required=True)
    psm.add_argument("--treatment", default="treated")
    psm.add_argument("--outcome", required=True)
    psm.add_argument("--post", default="post")
    psm.add_argument("--unit-id", default="unit_id")
    psm.add_argument("--time-col", default="period")
    psm.add_argument("--caliper", type=float, default=0.05)
    psm.set_defaults(func=_cmd_psm_did)

    placebo = sub.add_parser("placebo", help="in-space placebo test")
    placebo.add_argument("--panel", required=True)
    placebo.add_argument("--outcome", required=True)
    placebo.add_argument("--treatment", default="treated")
    placebo.add_argument("--post", default="post")
    placebo.add_argument("--unit-id", default="unit_id")
    placebo.add_argument("--time-col", default="period")
    placebo.add_argument("--simulations", type=int, default=100)
    placebo.add_argument("--seed", type=int, default=None)
    placebo.set_defaults(func=_cmd_placebo)

    evstudy = sub.add_parser("event-study", help="event study estimation")
    evstudy.add_argument("--panel", required=True)
    evstudy.add_argument("--outcome", required=True)
    evstudy.add_argument("--event-time", required=True)
    evstudy.add_argument("--treatment", default="treated")
    evstudy.add_argument("--unit-id", default="unit_id")
    evstudy.add_argument("--time-col", default="period")
    evstudy.set_defaults(func=_cmd_event_study)

    # dashboard
    dash = sub.add_parser("dashboard", help="launch the Streamlit research dashboard")
    dash.add_argument("--data-dir", default="data", help="root data directory")
    dash.add_argument("--port", type=int, default=8501)
    dash.add_argument("--host", default="0.0.0.0")
    dash.set_defaults(func=_cmd_dashboard)

    # dataset
    ds = sub.add_parser("dataset", help="assemble or inspect research datasets")
    ds_sub = ds.add_subparsers(dest="action", required=True)

    dsi = ds_sub.add_parser("info", help="summarize collected pipeline artifacts")
    dsi.add_argument("--data-dir", default="data")
    dsi.set_defaults(func=_cmd_dataset_info)

    dsp = ds_sub.add_parser("publish", help="assemble a self-contained published dataset")
    dsp.add_argument("--data-dir", default="data")
    dsp.add_argument("--out", required=True)
    dsp.add_argument("--title", default=None)
    dsp.add_argument("--author", action="append", default=[])
    dsp.add_argument("--version", default=None)
    dsp.add_argument("--csv", action="store_true", help="also write CSV copies")
    dsp.set_defaults(func=_cmd_dataset_publish)

    # reproduce
    repro = sub.add_parser("reproduce", help="run a paper reproduction")
    repro_sub = repro.add_subparsers(dest="study", required=True)

    jom = repro_sub.add_parser("jom2025", help="reproduce the JOM 2025 Steemit study")
    jom.add_argument("--out", default="data/reproductions/jom2025")
    jom.add_argument("--demo", action="store_true", help="run the synthetic-data demo")
    jom.add_argument("--data-dir", default="data/raw", help="dir with collected Steemit events")
    jom.add_argument("--event-time", default=None, help="treatment event time (ISO datetime)")
    jom.add_argument("--treated-file", default=None, help="file of treated user ids (one per line)")
    jom.add_argument("--placebo", type=int, default=100, help="number of in-space placebo simulations")
    jom.add_argument("--caliper", type=float, default=0.05, help="PSM caliper")
    jom.set_defaults(func=_cmd_reproduce_jom2025)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _cmd_collect_snapshot(args: argparse.Namespace) -> int:
    from onchaingov.collectors import SnapshotCollector

    collector = SnapshotCollector(Path(args.out), graphql_url=args.url)
    events = collector.run(args.space, since=args.since, collect_votes=not args.no_votes)
    path = collector.save(events, name=f"snapshot_{args.space}")
    print(f"collected {len(events)} events -> {path}")
    return 0


def _cmd_collect_tally(args: argparse.Namespace) -> int:
    from onchaingov.collectors import TallyCollector

    collector = TallyCollector(Path(args.out), graphql_url=args.url, api_key=args.api_key)
    events = collector.run(args.slug)
    path = collector.save(events, name=f"tally_{args.slug}")
    print(f"collected {len(events)} events -> {path}")
    return 0


def _cmd_collect_evm(args: argparse.Namespace) -> int:
    from onchaingov.collectors import EVMRPCCollector

    collector = EVMRPCCollector(Path(args.out), rpc_url=args.rpc, contract_address=args.contract)
    events = collector.run(
        from_block=args.from_block,
        to_block=args.to_block,
        event_name=args.event,
    )
    path = collector.save(events, name="evm_events")
    print(f"collected {len(events)} events -> {path}")
    return 0


def _cmd_collect_steemit(args: argparse.Namespace) -> int:
    from onchaingov.collectors import SteemitCollector

    collector = SteemitCollector(Path(args.out))
    events = collector.run(tag=args.tag, limit=args.limit, collect_votes=args.with_votes)
    path = collector.save(events, name=f"steemit_{args.tag}")
    print(f"collected {len(events)} events -> {path}")
    return 0


def _cmd_indicators(args: argparse.Namespace) -> int:
    import glob

    from onchaingov.indicators import participation_metrics

    files = sorted(glob.glob(str(Path(args.data_dir) / "*.parquet")))
    if not files:
        raise FileNotFoundError(f"no parquet files under {args.data_dir}")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        import polars as pl

        df = pl.read_parquet(f)
        if "event_type" not in df.columns:
            continue
        votes = df.filter(pl.col("event_type") == "vote")
        proposals = df.filter(pl.col("event_type") == "proposal")
        if votes.is_empty():
            continue
        metrics = participation_metrics(votes, proposals if not proposals.is_empty() else None)
        name = Path(f).stem
        out = out_dir / f"{name}_participation.parquet"
        metrics.write_parquet(out)
        print(f"indicators -> {out}")
    return 0


def _cmd_panel(args: argparse.Namespace) -> int:
    import glob

    import polars as pl

    from onchaingov.panel import PanelBuilder

    files = sorted(glob.glob(str(Path(args.data_dir) / "*.parquet")))
    if not files:
        raise FileNotFoundError(f"no parquet files under {args.data_dir}")
    frames = [pl.read_parquet(f) for f in files]
    events = pl.concat(frames, how="diagonal_relaxed")
    builder = PanelBuilder("unit_id", "period", freq=args.time)
    panel = builder.build(events)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "panel.parquet"
    panel.write_parquet(path)
    print(f"panel ({panel.height} rows) -> {path}")
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    import polars as pl

    from onchaingov.export import export_panel

    df = pl.read_parquet(args.input)
    path = export_panel(df, Path(args.out), fmt=args.format)
    print(f"exported -> {path}")
    return 0


def _cmd_attach_treatment(args: argparse.Namespace) -> int:
    import polars as pl

    from onchaingov.panel import attach_treatment

    df = pl.read_parquet(args.panel)
    treated_units = [
        line.strip()
        for line in Path(args.treated_file).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    out_df = attach_treatment(
        df,
        unit_id=args.unit_id,
        treated_units=treated_units,
        event_time=args.event_time,
        time_col=args.time_col,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out_df.write_parquet(out)
    print(f"attached treatment ({len(treated_units)} treated units) -> {out}")
    return 0


def _load_panel(args: argparse.Namespace):
    import polars as pl

    return pl.read_parquet(args.panel)


def _cmd_did(args: argparse.Namespace) -> int:
    from onchaingov.causal import did_estimate

    df = _load_panel(args)
    result = did_estimate(
        df,
        outcome=args.outcome,
        treatment=args.treatment,
        post=args.post,
        unit_id=args.unit_id,
        time_col=args.time_col,
    )
    print(result.summary_text())
    return 0


def _cmd_psm_did(args: argparse.Namespace) -> int:
    from onchaingov.causal import psm_did_estimate

    df = _load_panel(args)
    result, match = psm_did_estimate(
        df,
        outcome=args.outcome,
        treatment=args.treatment,
        post=args.post,
        unit_id=args.unit_id,
        time_col=args.time_col,
        caliper=args.caliper,
    )
    print(f"PSM matched {match.matched_n} rows, {match.control_n} control units")
    print(result.summary_text())
    return 0


def _cmd_placebo(args: argparse.Namespace) -> int:
    from onchaingov.causal import in_space_placebo

    df = _load_panel(args)
    result = in_space_placebo(
        df,
        outcome=args.outcome,
        treatment=args.treatment,
        post=args.post,
        unit_id=args.unit_id,
        time_col=args.time_col,
        n_simulations=args.simulations,
        seed=args.seed,
    )
    print(
        f"in-space placebo: mean pseudo-ATT {result.mean_placebo:.6f}, "
        f"empirical p-value {result.empirical_pvalue:.4f} "
        f"(passed={result.passed()})"
    )
    return 0


def _cmd_event_study(args: argparse.Namespace) -> int:
    from datetime import datetime

    from onchaingov.causal import event_study_estimate

    df = _load_panel(args)
    event_time = datetime.fromisoformat(args.event_time.replace("Z", "+00:00"))
    result = event_study_estimate(
        df,
        outcome=args.outcome,
        event_time=event_time,
        treatment=args.treatment,
        unit_id=args.unit_id,
        time_col=args.time_col,
    )
    print(f"event study: {len(result.relative_periods)} relative periods, nobs={result.nobs}")
    for r, c, s in zip(result.relative_periods, result.coefficients, result.std_errors):
        print(f"  rel {r:+d}: {c:.6f} (se {s:.6f})")
    return 0


def _cmd_dashboard(args: argparse.Namespace) -> int:
    import os
    import subprocess
    import sys

    try:
        from onchaingov.dashboard import APP_PATH
    except ImportError as exc:
        raise ImportError("dashboard extras not installed; run `pip install -e '.[dashboard]'`") from exc
    env = {**os.environ, "ONCHAGOV_DATA_DIR": args.data_dir}
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(APP_PATH), "--server.port", str(args.port),
        "--server.address", args.host,
    ]
    print(f"launching dashboard at http://{args.host}:{args.port} (data dir: {args.data_dir})")
    return subprocess.call(cmd, env=env)


def _cmd_dataset_info(args: argparse.Namespace) -> int:
    import json

    from onchaingov.dataset import summarize_data_dir

    summary = summarize_data_dir(args.data_dir)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    total = sum(len(files) for files in summary.values())
    print(f"total artifacts: {total}")
    return 0


def _cmd_dataset_publish(args: argparse.Namespace) -> int:
    from onchaingov.dataset import publish_dataset

    manifest = publish_dataset(
        args.data_dir,
        args.out,
        title=args.title,
        authors=args.author or None,
        version=args.version,
        with_csv=args.csv,
    )
    print(f"published dataset -> {args.out} (version {manifest['version']})")
    for sub, files in manifest["files"].items():
        print(f"  {sub}: {len(files)} files")
    return 0


def _cmd_reproduce_jom2025(args: argparse.Namespace) -> int:
    from datetime import datetime

    if args.demo:
        from onchaingov.reproductions import run_demo

        summary = run_demo(out_dir=args.out, n_placebo=args.placebo)
        print(f"JOM 2025 reproduction (synthetic demo) -> {args.out}")
    else:
        from onchaingov.reproductions import run_from_steemit_events

        event_time = None
        if args.event_time:
            event_time = datetime.fromisoformat(args.event_time.replace("Z", "+00:00"))
        summary = run_from_steemit_events(
            args.data_dir,
            out_dir=args.out,
            event_time=event_time,
            treated_file=args.treated_file,
            n_placebo=args.placebo,
            caliper=args.caliper,
        )
        print(f"JOM 2025 reproduction (Steemit events) -> {args.out}")
    print(f"ATT: {summary['att']:.6f} (p={summary['att_pvalue']:.4f}), matched rows: {summary['matched_units']}")
    if summary.get("event_study") is not None:
        print(f"event study pre-trends p-value: {summary['event_study'].pre_trends_pvalue():.4f}")
    if summary.get("placebo") is not None:
        print(
            f"in-space placebo empirical p-value: {summary['placebo'].empirical_pvalue:.4f} "
            f"(passed={summary['placebo'].passed()})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
