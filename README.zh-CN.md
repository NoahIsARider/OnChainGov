# OnChainGov

面向 DAO/Web3 治理研究的开源全流程工具链——从原始治理数据到研究就绪的面板数据 + 因果推断（DID/PSM-DID）一键导出。

## 特性

- **多源采集**: Snapshot/Tally GraphQL + EVM RPC + Steemit
- **研究级指标库**: 治理参与度、投票权集中度、代币激励四维指标（creation/curation/novelty/ownership share）
- **因果推断模板**: DID、PSM-DID、placebo 检验、事件研究
- **面板数据导出**: Parquet/CSV + 论文图表
- **复现库**: JOM 2025 Steemit 论文复现 (v2)

## 安装

```bash
pip install -e ".[dev]"
```

## 快速开始

```bash
# 采集 Snapshot 数据
onchaingov collect snapshot --space <space> --since 2024-01-01 --out data/raw

# 计算指标
onchaingov indicators --data-dir data/raw --out data/indicators

# 构建面板并运行 DID
onchaingov panel --unit user --time week --out data/panels
onchaingov did --panel data/panels/panel.parquet --treatment treated --outcome outcome_activity
```

## 文档

- [INDEX.md](docs/INDEX.md) - 项目概述
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - 架构设计
- [INTERFACES.md](docs/INTERFACES.md) - 接口定义
- [DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) - 开发指南

## 许可证

MIT
