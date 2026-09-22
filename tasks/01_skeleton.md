# Phase 01 — Skeleton

## 目标

建立最小项目骨架。

不要实现完整 Agent 行为。

## 需要完成

- package 结构
- 最小 CLI entry point
- config skeleton
- tests 目录
- 基础 import 可用

建议结构可参考：

```text
src/<package>/
    cli.py
    agent/
    models/
    tools/
    workspace.py
    config.py
    trajectory.py

tests/
```

实际以 Phase 00 确认方案为准。

## 验证

至少：

```bash
uv run python -c "import <package>"
uv run my-agent --help
```

## 依赖

只加当前阶段确实需要的依赖。

如需要：

- Typer / Click
- Rich
- dotenv
- Pydantic

先说明用途，再 `uv add`。

## 本阶段禁止

不要：

- 实现完整 Tool
- 实现 Model provider
- 实现 Agent Loop
- 调真实 LLM API
- 做 CLI 美化
- 自动进入 Phase 02

完成后停止。
