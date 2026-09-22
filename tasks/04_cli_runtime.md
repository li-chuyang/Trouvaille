# Phase 04 — CLI + Runtime

## 目标

把已有 Agent Core 变成真正可用的 CLI Coding Agent MVP。

## CLI

至少支持：

```bash
my-agent
```

进入交互模式。

## CLI 显示

至少显示：

- 当前 step
- tool name
- 关键 tool arguments
- tool success / failure
- 最终回答

不要输出巨大原始 JSON。

## CLI 视觉

严格遵守：

```text
CLI_DESIGN.md
```

如果该文件仍处于占位状态：

- 保持简单
- 不自行设计最终 Logo
- 不自行决定最终主题色
- 不做复杂 ASCII Art
- 不做复杂 TUI

CLI presentation 与 Agent Core 分离。

## Tool 补齐

MVP 最终至少有：

- list_files
- search
- read_file
- write_file
- edit_file
- shell
- git_diff

## Trajectory

至少记录：

- task
- step
- model response
- tool calls
- tool results
- final answer

可用 JSON / JSONL。

## Runtime errors

友好处理：

- missing API key
- model API error
- Ctrl+C
- max_steps
- invalid workspace

## E2E

至少验证：

A. 查看目录并回答结构  
B. 创建一个简单 Python 文件并运行  
C. 修改一个已有文件并运行验证

## 本阶段禁止

不要：

- 复杂 TUI
- planner
- context compact
- repo graph
- subagent
- 自动进入 Phase 05

完成后停止。
