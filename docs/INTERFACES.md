# 接口定义

OnChainGov 作为 Python 包 + CLI 交付，接口分为三类：CLI 命令、Python API、数据格式契约。

## CLI 命令

通过 `onchaingov` 命令入口（`pyproject.toml` 中配置 `[project.scripts]`）。

### 数据采集

| 命令 | 参数 | 说明 |
|------|------|------|
| `onchaingov collect snapshot` | `--space`, `--since`, `--out` | 采集 Snapshot 空间全部提案与投票 |
| `onchaingov collect tally` | `--org`, `--since`, `--out` | 采集 Tally 组织治理数据 |
| `onchaingov collect evm` | `--rpc`, `--contract`, `--from-block`, `--to-block` | 采集链上代币/投票合约事件 |
| `onchaingov collect steemit` | `--since`, `--until`, `--out` | 采集 Steemit 链上内容与代币数据 (v2) |

### 指标与面板

| 命令 | 参数 | 说明 |
|------|------|------|
| `onchaingov indicators` | `--data-dir`, `--out` | 计算全部治理/激励指标 |
| `onchaingov panel` | `--unit`, `--time`, `--out` | 构建面板数据 |
| `onchaingov export` | `--format [parquet|csv]`, `--out` | 导出研究数据 |

### 因果推断

| 命令 | 参数 | 说明 |
|------|------|------|
| `onchaingov did` | `--panel`, `--treatment`, `--outcome` | 双重差分估计 |
| `onchaingov psm-did` | `--panel`, `--treatment`, `--outcome`, `--covariates` | PSM-DID (v2) |
| `onchaingov placebo` | `--panel`, `--treatment`, `--outcome`, `--iterations` | placebo 检验 |
| `onchaingov event-study` | `--panel`, `--event` | 事件研究 |

### 复现与仪表盘

| 命令 | 参数 | 说明 |
|------|------|------|
| `onchaingov reproduce jom2025` | `--out` | 复现 JOM 2025 Steemit 论文 (v2) |
| `onchaingov dashboard` | `--data-dir` | 启动 Streamlit 仪表盘 (v3) |

## Python API

### 采集器基类

```python
from onchaingov.collectors.base import Collector, RawEvent

class SnapshotCollector(Collector):
    """采集器需实现 run()，返回统一 RawEvent 流。"""

    def run(self, since: str, out: Path) -> None: ...
```

### 指标库

```python
from onchaingov.indicators.participation import participation_metrics
from onchaingov.indicators.concentration import herfindahl, gini
from onchaingov.indicators.token_incentive import (
    creation_metric, curation_metric,
    novelty_metric, ownership_share,
)
```

### 因果推断

```python
from onchaingov.causal.did import DIDEstimator
from onchaingov.causal.psm_did import PSMDIDEstimator
from onchaingov.causal.placebo import placebo_test

est = DIDEstimator(treatment_col="treated", outcome_col="activity")
result = est.fit(panel_df)          # 返回 linearmodels 结果
att = result.params["treated"]      # 处理效应估计
```

### 面板构建

```python
from onchaingov.panel.builder import PanelBuilder

pb = PanelBuilder(unit_id="user", time="period")
panel = pb.build(events_df, indicators_df)
```

## 数据格式契约

### 原始事件 (RawEvent)

统一字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | str | 数据来源 (snapshot/tally/evm/steemit) |
| `event_type` | str | proposal/vote/token_transfer/... |
| `entity_id` | str | 主体标识（用户/空间/提案） |
| `entity_address` | str | 链上地址（若有） |
| `timestamp` | datetime | 事件时间 (UTC) |
| `payload` | json | 各源原始载荷 |
| `raw` | json | 完整原始响应，用于审计 |

### 面板数据结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `unit_id` | str | 面板单元（用户/DAO） |
| `period` | datetime | 时间维度（日/周/月） |
| `treated` | int | 处理组标记 (0/1) |
| `post` | int | 处理期标记 (0/1) |
| `outcome_*` | float | 各结果变量 |
| `covariate_*` | float | 协变量 |
| `weight` | float | 匹配权重 (PSM-DID) |

### 输出目录约定

```
data/
├── raw/          # 原始采集数据 (Parquet)
├── normalized/   # 标准化事件 (Parquet)
├── indicators/   # 指标计算结果 (Parquet)
└── panels/       # 面板数据 (Parquet/CSV)
```
