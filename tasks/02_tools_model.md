# Phase 02 — Model + Tools

## 目标

建立：

1. Model abstraction
2. Tool abstraction / registry
3. Workspace

先不实现完整 Agent Loop。

## Model

第一版只实现一个 provider。

要求：

- Agent 不直接强耦合某个 SDK
- provider 配置来自 config / env
- 模型响应转成项目内部统一结构

不要现在同时支持很多 provider。

## Tools

建立 Tool abstraction 和 registry。

第一批工具：

- list_files
- read_file
- write_file
- search
- shell

`edit_file` 和 `git_diff` 可视实现复杂度稍后补齐。

## Workspace

要求：

- file tool 相对 workspace root
- resolve 后仍验证路径在 root 内
- shell cwd = workspace
- shell 有基础 timeout
- stdout / stderr / exit code 可返回

## Error

Tool error 应成为统一 result / observation，而不是直接把整个程序打崩。

## Tests

至少测试：

- path traversal 被拒绝
- read/write 正常
- search 正常
- shell 成功
- shell 非零 exit code
- unknown tool
- invalid args

Model provider 可 mock。

## 本阶段禁止

不要：

- 实现完整 Agent Loop
- planner
- context compact
- CLI 美化
- 自动进入 Phase 03

完成后停止。
