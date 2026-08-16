# 开发指南

## 环境要求

- Python 3.10+ (推荐 3.11)
- [uv](https://docs.astral.sh/uv/) 或 pip
- 网络访问（Snapshot/Tally GraphQL API、EVM RPC 节点）
- Jupyter (复现库用)

## 快速开始

```bash
# 1. 克隆仓库
git clone <repo-url> && cd onchaingov

# 2. 创建虚拟环境并安装
uv sync
# 或: python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"

# 3. 采集 Snapshot 数据
onchaingov collect snapshot --space <space> --since 2024-01-01 --out data/raw

# 4. 计算指标
onchaingov indicators --data-dir data/raw --out data/indicators

# 5. 构建面板并运行 DID
onchaingov panel --unit user --time week --out data/panels
onchaingov did --panel data/panels/panel.parquet --treatment treated --outcome outcome_activity
```

## 项目结构说明

- `src/onchaingov/collectors/` — 数据采集器，新增数据源在此添加并继承 `Collector` 基类
- `src/onchaingov/indicators/` — 指标计算函数，纯函数式、输入输出均为 polars DataFrame
- `src/onchaingov/causal/` — 因果推断模板，封装 linearmodels 与 scikit-learn
- `src/onchaingov/panel/` — 面板构建逻辑
- `src/onchaingov/export/` — 导出与图表
- `src/onchaingov/reproductions/` — 论文复现 (v2)
- `notebooks/` — 使用示例与复现 notebook
- `dashboard/` — Streamlit 仪表盘 (v3)
- `data/` — 数据目录，**已 gitignore，不提交**

## 开发规范

### 命名规范
- Python 遵循 PEP8，snake_case
- 指标函数以指标名命名，如 `herfindahl`、`gini`、`creation_metric`
- 采集器以数据源命名，如 `SnapshotCollector`

### 代码风格
- 类型注解必须完整
- 指标函数保持纯函数式，不产生副作用
- 所有 DataFrame 操作使用 polars API

### 提交规范
- 使用 Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`
- 示例: `feat(indicators): add voting concentration metrics`

## 常见任务

### 新增一个数据源
1. 在 `src/onchaingov/collectors/` 新建 `xxx.py`
2. 继承 `Collector` 基类，实现 `run()`
3. 在 `src/onchaingov/normalizers/schemas.py` 注册事件类型映射
4. 在 CLI (`cli.py`) 注册 `collect xxx` 子命令
5. 编写测试 `tests/test_collectors_xxx.py`

### 新增一个指标
1. 在对应模块添加纯函数
2. 输入输出使用 polars DataFrame，遵循已有签名风格
3. 补充单元测试与 docstring 中的公式说明

### 新增一个因果推断模板
1. 在 `src/onchaingov/causal/` 添加模块
2. 封装为 Estimator 类，`fit()` 返回标准结果对象
3. 在 `notebooks/` 添加使用示例

## 测试

```bash
# 运行全部测试
pytest

# 运行指定模块
pytest tests/test_indicators.py -v
```

测试要求：
- 采集器测试使用 mock 数据，不依赖真实网络
- 指标函数必须有数值正确性测试（用已知答案的构造数据）
- 因果推断测试用合成数据验证估计方向

## 构建与发布

### 本地构建

```bash
# 构建 wheel
uv build
# 或: python -m build

# 运行 lint 与类型检查
ruff check src/onchaingov
mypy src/onchaingov
```

### 版本管理
- 遵循 Semantic Versioning
- MVP (1.0.0)：Snapshot 采集 + 核心指标 + DID
- v2 (2.0.0)：Steemit 模块 + PSM-DID + JOM 复现
- v3 (3.0.0)：多平台 + 仪表盘 + 数据集发布

### 发布
- 通过 `uv publish` 或 twine 发布到 PyPI
- 数据集发布与论文复现归档见 v3 路线图
