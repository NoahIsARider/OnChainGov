"""OnChainGov research dashboard (Streamlit).

Interactive panels for exploring raw governance data, computing indicators,
building panels, and running causal inference templates (DID / PSM-DID /
placebo / event study) with paper charts.

Launch with:

    onchaingov dashboard [--data-dir data]

or directly with ``streamlit run src/onchaingov/dashboard/app.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import polars as pl
import streamlit as st

DEFAULT_DATA_DIR = os.environ.get("ONCHAGOV_DATA_DIR", "data")


def _data_dir() -> Path:
    return Path(st.sidebar.text_input("Data directory", value=DEFAULT_DATA_DIR))


def _parquet_files(root: Path, sub: str) -> list[Path]:
    d = root / sub
    return sorted(d.glob("*.parquet")) if d.exists() else []


def _load_first(root: Path, sub: str) -> pl.DataFrame | None:
    files = _parquet_files(root, sub)
    if not files:
        return None
    return pl.read_parquet(files[0])


def _empty_hint(files: list[Path]) -> None:
    if not files:
        st.info("No files found. Collect data first with `onchaingov collect ...`.")


def overview_page(root: Path) -> None:
    st.header("Overview")
    st.markdown(
        "OnChainGov is an open-source research toolchain for DAO/Web3 governance: "
        "from raw governance data to research-ready panel data and causal inference "
        "(DID / PSM-DID) with one-click export."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Raw event files", len(_parquet_files(root, "raw")))
    c2.metric("Indicator files", len(_parquet_files(root, "indicators")))
    c3.metric("Panel files", len(_parquet_files(root, "panels")))
    c4.metric("Reproductions", len(_parquet_files(root, "reproductions")))
    st.divider()
    st.markdown(
        "**Pipeline**: collect (Snapshot/Tally/EVMS/Steemit) → normalize → indicators "
        "→ panel → causal inference (DID/PSM-DID/placebo/event study) → export + charts."
    )


def raw_page(root: Path) -> None:
    st.header("Raw data")
    files = _parquet_files(root, "raw")
    _empty_hint(files)
    if not files:
        return
    names = [f.name for f in files]
    chosen = st.selectbox("File", names)
    df = pl.read_parquet(root / "raw" / chosen)
    st.caption(f"{df.height} rows x {df.width} columns")
    st.dataframe(df.head(500), use_container_width=True)


def indicators_page(root: Path) -> None:
    st.header("Indicators")
    files = _parquet_files(root, "indicators")
    _empty_hint(files)
    if not files:
        return
    names = [f.name for f in files]
    chosen = st.selectbox("Indicator file", names)
    df = pl.read_parquet(root / "indicators" / chosen)
    st.dataframe(df, use_container_width=True)

    st.subheader("On-demand concentration metrics")
    raw = _load_first(root, "raw")
    if raw is not None and "vp" in raw.columns:
        from onchaingov.indicators import concentration_by_group

        try:
            conc = concentration_by_group(raw, value_col="vp", group_col="space_id")
            st.dataframe(conc, use_container_width=True)
        except (ValueError, KeyError) as exc:
            st.warning(str(exc))
    else:
        st.info("Load a vote frame with a `vp` column to compute concentration metrics.")


def panel_page(root: Path) -> None:
    st.header("Panel builder")
    st.markdown(
        "Build a balanced unit-period panel from raw events, or load an existing panel."
    )
    cols = st.columns(4)
    unit_col = cols[0].text_input("Unit column", value="user")
    freq = cols[1].selectbox("Frequency", ["day", "week", "month"])
    build = cols[2].button("Build panel")
    load_existing = cols[3].button("Load panel.parquet")

    if build:
        raw = _load_first(root, "raw")
        if raw is None:
            st.error("No raw data available.")
        else:
            from onchaingov.panel import PanelBuilder

            builder = PanelBuilder(unit_col, "period", freq=freq)
            try:
                panel = builder.build(raw)
                (root / "panels").mkdir(parents=True, exist_ok=True)
                panel.write_parquet(root / "panels" / "panel.parquet")
                st.success("Panel built and saved to data/panels/panel.parquet")
                _show_panel(panel)
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))

    if load_existing:
        panel_path = root / "panels" / "panel.parquet"
        if panel_path.exists():
            _show_panel(pl.read_parquet(panel_path))
        else:
            st.warning("No panel.parquet found under data/panels/.")


def _show_panel(panel: pl.DataFrame) -> None:
    st.caption(f"{panel.height} rows x {panel.width} columns")
    st.dataframe(panel.head(500), use_container_width=True)
    if "period" in panel.columns:
        n_units = panel["unit_id"].n_unique() if "unit_id" in panel.columns else None
        st.write(f"Periods: {panel['period'].min()} to {panel['period'].max()}")
        if n_units:
            st.write(f"Units: {n_units}")


def causal_page(root: Path) -> None:
    st.header("Causal inference")
    panel_path = root / "panels" / "panel.parquet"
    if not panel_path.exists():
        st.info("Build or provide a panel first (see the Panel tab).")
        return
    panel = pl.read_parquet(panel_path)

    outcome = st.selectbox("Outcome", [c for c in panel.columns if c not in ("unit_id", "period", "treated", "post")] or panel.columns)
    method = st.radio("Method", ["DID", "PSM-DID", "In-space placebo", "Event study"])
    run = st.button("Run estimation")

    if not run:
        st.dataframe(panel.head(200), use_container_width=True)
        return

    try:
        if method == "DID":
            from onchaingov.causal import did_estimate

            res = did_estimate(panel, outcome=outcome, treatment="treated", post="post")
            st.code(res.summary_text())
        elif method == "PSM-DID":
            from onchaingov.causal import psm_did_estimate

            covs = [c for c in panel.columns if c.startswith("covariate_")]
            if not covs:
                st.warning("No `covariate_*` columns found; PSM will not match.")
            res, match = psm_did_estimate(
                panel, outcome=outcome, treatment="treated", post="post",
                covariates=covs or None, caliper=0.1,
            )
            st.write(f"Matched {match.matched_n} rows, {match.control_n} control units")
            st.code(res.summary_text())
        elif method == "In-space placebo":
            from onchaingov.causal import in_space_placebo

            pb = in_space_placebo(
                panel, outcome=outcome, treatment="treated", post="post",
                n_simulations=st.slider("Simulations", 20, 200, 100, key="pb_n"),
            )
            st.write(
                f"mean pseudo-ATT {pb.mean_placebo:.6f}, empirical p-value "
                f"{pb.empirical_pvalue:.4f} (passed={pb.passed()})"
            )
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots()
            ax.hist(pb.placebo_estimates, bins=30, alpha=0.7)
            if pb.true_att is not None:
                ax.axvline(pb.true_att, color="red", ls="--", label="true ATT")
            ax.legend()
            st.pyplot(fig)
        else:  # event study
            from datetime import datetime

            from onchaingov.causal import event_study_estimate

            ev_time = st.text_input("Event time (ISO)", value="2024-06-01T00:00:00")
            res = event_study_estimate(
                panel, outcome=outcome,
                event_time=datetime.fromisoformat(ev_time.replace("Z", "+00:00")),
                treatment="treated",
            )
            st.write(f"pre-trends p-value: {res.pre_trends_pvalue():.4f}")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots()
            ax.errorbar(
                res.relative_periods, res.coefficients,
                yerr=[1.96 * s for s in res.std_errors], fmt="o", capsize=3,
            )
            ax.axhline(0, color="black", lw=0.8, ls="--")
            ax.axvline(-1, color="grey", lw=0.8, ls=":")
            ax.set_xlabel("Relative period")
            ax.set_ylabel("Estimate")
            st.pyplot(fig)
    except (ValueError, RuntimeError, ImportError) as exc:
        st.error(str(exc))


def reproductions_page(root: Path) -> None:
    st.header("Reproductions")
    st.markdown(
        "Run the JOM 2025 Steemit reproduction (governance vs. tradeable token "
        "incentives, PSM-DID) as a sanity check of the toolchain."
    )
    if st.button("Run synthetic JOM 2025 demo"):
        with st.spinner("Running PSM-DID reproduction..."):
            from onchaingov.reproductions import run_demo

            summary = run_demo(out_dir=root / "reproductions" / "jom2025", n_placebo=100)
        st.success("Reproduction complete.")
        st.write(f"**ATT** on {summary['config'].outcome_col}: "
                 f"{summary['att']:.6f} (p={summary['att_pvalue']:.4f})")
        st.write(f"Matched sample: {summary['matched_units']} rows")
        if summary.get("placebo") is not None:
            st.write(f"Placebo empirical p-value: {summary['placebo'].empirical_pvalue:.4f}")
        for name in ("att.png", "event_study.png", "placebo.png"):
            p = root / "reproductions" / "jom2025" / name
            if p.exists():
                st.image(str(p), caption=name)
    elif _parquet_files(root, "reproductions"):
        st.info("Reproduction artifacts exist under data/reproductions/. Inspect summary.txt:")


def main() -> None:
    st.set_page_config(page_title="OnChainGov", layout="wide")
    st.sidebar.title("OnChainGov")
    st.sidebar.caption("DAO governance research toolchain")
    root = _data_dir()

    tab = st.sidebar.radio(
        "Page",
        ["Overview", "Raw data", "Indicators", "Panel", "Causal inference", "Reproductions"],
    )
    pages = {
        "Overview": overview_page,
        "Raw data": raw_page,
        "Indicators": indicators_page,
        "Panel": panel_page,
        "Causal inference": causal_page,
        "Reproductions": reproductions_page,
    }
    pages[tab](root)


if __name__ == "__main__":
    main()
