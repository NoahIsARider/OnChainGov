# OnChainGov

Open-source, end-to-end research toolchain for DAO/Web3 governance — from raw governance data to research-ready panel data and causal inference (DID / PSM-DID) with one-click export.

## Features

- **Multi-source collection**: Snapshot / Tally GraphQL, EVM RPC, Steemit
- **Research-grade indicator library**: governance participation, voting-power concentration, and four-dimensional token incentives (creation / curation / novelty / ownership share)
- **Causal inference templates**: DID, PSM-DID, placebo tests (in-time / in-space), event study
- **Panel data export**: Parquet / CSV + paper-quality charts
- **Reproduction library**: JOM 2025 Steemit study reproduction (v2)

## Installation

```bash
pip install -e ".[dev]"
```

## Quick Start

```bash
# Collect Snapshot data
onchaingov collect snapshot --space <space> --since 2024-01-01 --out data/raw

# Compute indicators
onchaingov indicators --data-dir data/raw --out data/indicators

# Build a panel and run DID
onchaingov panel --unit user --time week --out data/panels
onchaingov did --panel data/panels/panel.parquet --treatment treated --outcome outcome_activity
```

## Documentation

- [INDEX.md](docs/INDEX.md) — project overview
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — architecture design
- [INTERFACES.md](docs/INTERFACES.md) — interface definitions
- [DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) — developer guide

## License

MIT
