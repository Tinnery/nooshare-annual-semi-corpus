# nooshare-annual-semi-corpus — Agent 工作规则

本仓库负责 A 股年报/半年报 Markdown 语料的独立登记与质量管理。

## Matrix Authority

- **nooshare-design**：系统角色与跨仓逻辑职责（architecture/matrix.md）。
- **nooshare-noos**：适用的已验证知识与工程 invariant。
- **nooshare-workenv**：工作区、主机、部署与操作授权（AGENTS.md、workspace.yaml）。

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

## 文档与结构权威

本仓库不内联结构纪律正文，也不维护第二份文档注册表。按权威引用：

| 关注点 | 权威 | 读什么 |
|--------|------|--------|
| 结构纪律（Git 唯一记录、平铺、按需建目录、AGENTS.md 职责） | nooshare-workenv | `AGENTS.md` |
| 文档体系归属与维护边界 | nooshare-design | `nooshare-design/doc-index/nooshare-annual-semi-corpus.md` |

通过 `workspace.yaml` 定位目标 Repo 的 checkout 路径后读取对应文件。

**不重复叙述**：代码已表达的参数和失败语义，不再维护第三份重复说明。数据安全约束、数据库写入规则、数据契约和恢复要求仍应留下必要说明。

## Checks

```bash
# 离线测试
uv run pytest tests/ -v

# CLI 结构自检
uv run nooshare-annual-semi-corpus --help
```
