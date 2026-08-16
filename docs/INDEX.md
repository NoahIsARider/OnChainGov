# OnChainGov 文档

## 项目概述

OnChainGov 是一个面向 DAO/Web3 治理研究的开源全流程工具链，定位是「从原始治理数据到研究就绪的面板数据 + 因果推断」的一站式管道。它将研究者一次性手搓的数据管线（如方钰麟 JOM 2025 论文中的 Steemit 案例）变成可复现、可扩展的研究基础设施。

**目标用户**: IS/OM 领域的实证研究者（尤其关注 DAO 治理、代币激励方向的学者）、DAO 数据科学家、治理研究人员。

**核心价值**:
- **研究级指标层**: 区别于 Dune/DeepDAO/Boardroom 等商业仪表盘，提供治理参与度、投票权集中度、代币激励（creation、curation、novelty、ownership share）等研究就绪指标库
- **因果推断模板**: 内置 DID、PSM-DID、placebo 检验模板，降低计量经济学的实现门槛
- **论文复现库**: 内置方钰麟 JOM 2025 论文复现 notebook（Steemit 98,000 用户，PSM-DID），作为 sanity check，把论文变成「活文档」
- **面板数据一键导出**: 支持 Parquet/CSV 格式导出，可直接用于 Stata/R/Python 计量流程

## 技术选型

| 类别 | 选择 | 理由 |
|------|------|------|
| 编程语言 | Python 3.10+ | 生态覆盖 web3、计量、机器学习 |
| 链上数据 | web3.py | Ethereum EVM 链上数据读取 |
| 治理数据 | GraphQL (Snapshot/Tally) | 治理平台的官方查询接口 |
| 数据处理 | polars | 列式、内存高效，适合大规模面板数据 |
| 因果推断 | linearmodels | DID/面板计量专用库 |
| PSM 匹配 | scikit-learn | 倾向得分匹配的成熟实现 |
| 仪表盘 | Streamlit | 快速构建研究交互面板 |
| 数据存储 | Parquet / CSV | 研究场景的标准可交换格式 |

## 核心功能

### ① 数据采集器
- **目的**: 采集多来源原始治理数据
- **描述**: Snapshot/Tally GraphQL 采集器 + 链上 RPC 数据源 + Steemit 区块链采集器，统一原始数据落地格式

### ② 治理与激励指标库
- **目的**: 计算研究就绪的治理/激励指标
- **描述**: 治理参与度、投票权集中度（Herfindahl/Gini）、代币激励四维指标（creation、curation、novelty、ownership share）

### ③ 因果推断模板
- **目的**: 提供标准计量流程
- **描述**: DID（双重差分）、PSM-DID（倾向得分匹配 + 双重差分）、placebo 检验、事件研究模板

### ④ 面板数据导出与论文图表
- **目的**: 打通「研究数据 → 论文输出」
- **描述**: 面板数据导出（Parquet/CSV）+ 论文级图表生成

### ⑤ 复现库
- **目的**: 复现旗舰论文作为 sanity check
- **描述**: 内置方钰麟 JOM 2025 论文复现 notebook（Steemit 治理代币 vs 交易代币激励效果）

## 路线图

| 阶段 | 范围 | 交付物 |
|------|------|--------|
| MVP | Snapshot 采集 + 核心指标 + DID | 可用的端到端管道 + 因果推断模板 |
| v2 | Steemit 模块 + PSM + 复现 JOM | PSM-DID + 论文复现 notebook |
| v3 | 多平台 + 仪表盘 + 发布数据集 | Streamlit 仪表盘 + 公开数据集发布 |

## 文档导航

- [架构设计](./ARCHITECTURE.md) - 系统架构和技术设计
- [接口定义](./INTERFACES.md) - 接口和交互规范
- [开发指南](./DEVELOPER_GUIDE.md) - 开发环境和规范
