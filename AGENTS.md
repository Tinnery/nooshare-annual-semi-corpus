# nooshare-annual-semi-corpus — Agent 工作规则

本仓库负责独立登记、评估和管理 A 股年报及半年报 Markdown 语料的质量状态。

**核心定位**：Corpus Registry & Quality Management

- **Inventory**：知道有哪些 Markdown、对应哪个报告、内容 Hash 是什么
- **Coverage**：检查预期报告与实际语料之间的缺口
- **Assessment**：判断文件内容是否完整、可靠、适合下游使用
- **Curation**：记录保留、复核、重新转换、重新采集等处理建议

## Matrix Authority

- **nooshare-design**：系统角色与跨仓逻辑职责（architecture/matrix.md）。
- **nooshare-noos**：适用的已验证知识与工程 invariant。
- **nooshare-workenv**：工作区、主机、部署与操作授权（AGENTS.md、workspace.yaml）。

修改上述权威拥有的关注点前，先读对应权威的现行规则。

## Context Bootstrap

任务涉及以下情形时，向上索引对应权威：

| 触发条件 | 索引目标 | 读什么 |
|----------|----------|--------|
| 系统角色 / 跨仓职责变更 | nooshare-design | `architecture/matrix.md` |
| 工程 invariant / 已验证知识 | nooshare-noos | 相关 domain 文件 |
| 主机 / 部署 / 操作授权变更 | nooshare-workenv | `AGENTS.md` + `workspace.yaml` |

索引路径：通过 `workspace.yaml` 找到目标 Repo 的 checkout 路径，读取对应文件。

## Local Ownership

本仓库拥有：

- Python 源码（`annual_semi_corpus/`）
- CLI 命令（`annual_semi_corpus/cli.py`）
- 语料清单与质量评估产物（运行时生成，不纳入版本控制）
- 测试（`tests/`）

上游权威不替代这些本地契约。与权威要求冲突时，向拥有该问题的权威反馈，不在本地悄悄改写权威定义。

## Current Workflow

唯一执行入口是 CLI（`annual_semi_corpus/cli.py`）。

| 命令 | 状态 | 说明 |
|------|------|------|
| `inventory` | Current | 扫描实际 Markdown，建立语料清单 |
| `assess` | Current | 对指定清单进行质量评估 |
| `diff` | Current | 比较两次语料清单或质量评估的变化 |

**边界**：

- 不生产、不修改、不发布正式 Markdown。
- 不复制 Producer 已有的完整性数据库和算法。
- 不重新实现 Extraction 的章节识别，也不负责 Research 的事实提取。
- 拥有自己的语料清单和质量评估记录，但不拥有原始 Markdown 对象。

## Operational Boundaries

服从 Workenv 操作约束：

- **STABLE 写入**（生产数据库、RustFS 对象存储）必须获得明确授权
- **凭据操作**（轮换、删除）必须按 Workenv 凭据隔离规则执行
- **正式发布**必须获得明确授权，并在 commit trailer 用 `Authorized-by:` 留痕
- **破坏性操作**（删除生产数据、重建 Schema）前必须确认恢复点

## Test & Verification

运行测试：

```bash
uv run pytest
```

验证约束：

- 离线测试（不涉及生产数据库）可直接运行
- 涉及 DEV / VALIDATION / STABLE 的测试需明确环境标识
- 生产数据不允许用于测试

## Document Routing

**当前权威文档**：

- `README.md`：项目基本介绍与快速入口
- `docs/decisions/`：架构决策记录（ADR），用于记录重要技术决策及其理由
- `docs/migrations/`：数据迁移记录，用于记录 Schema 变更与数据迁移过程

**不重复叙述**：代码已表达的参数和失败语义，不再维护第三份重复说明。数据安全约束、数据库写入规则、数据契约和恢复要求仍应留下必要说明。

## Checks

```bash
# 离线测试
uv run pytest tests/ -v

# CLI 结构自检
uv run nooshare-annual-semi-corpus --help
```
