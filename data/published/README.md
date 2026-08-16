# Demo DAO governance dataset

Research-ready DAO governance panel dataset assembled by OnChainGov.

## Metadata

- Version: 0.1.0
- Generated: 2026-08-16T06:22:02Z
- Toolchain: onchaingov 0.1.0 (commit ace26bf)

## Contents

### raw

| file | rows | bytes |
|------|------|-------|
| snapshot_space_a.parquet | 128 | 3969 |

### indicators

| file | rows | bytes |
|------|------|-------|
| snapshot_space_a_participation.parquet | 1 | 2539 |

### panels

| file | rows | bytes |
|------|------|-------|
| panel.parquet | 120 | 1358 |
| panel_treated.parquet | 120 | 2030 |

### reproductions

| file | rows | bytes |
|------|------|-------|
| jom2025/matched_panel.parquet | 3332 | 109441 |
| jom2025/propensity_scores.parquet | 300 | 9191 |
| jom2025/reproduction_panel.parquet | 4200 | 136586 |
| jom2025/synthetic_panel.parquet | 4200 | 136586 |

## Reproducibility

This dataset was produced by OnChainGov (https://github.com/NoahIsARider/OnChainGov). Re-run the pipeline with:

```bash
onchaingov collect ...   # collect raw events
onchaingov indicators --data-dir data/raw --out data/indicators
onchaingov panel --data-dir data/raw --out data/panels
onchaingov did --panel data/panels/panel.parquet --outcome outcome_*
onchaingov reproduce jom2025 --demo --out data/reproductions/jom2025
```
