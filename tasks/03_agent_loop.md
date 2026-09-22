# Phase 03 — Agent Loop

## 目标

实现本项目最核心的：

> 自己的 Agent Loop

## 核心流程

```text
system + user task
        ↓
model.generate()
        ↓
assistant response
        ↓
有 tool calls？
   ├── 否 → final answer
   └── 是
        ↓
dispatch tool calls
        ↓
tool results
        ↓
append observations
        ↓
next step
```

## Agent 至少接收

- task
- model
- tools
- workspace
- max_steps

## Messages

至少支持：

- system
- user
- assistant
- tool result

不要现在加入：

- compact
- memory
- planner
- context ranking

## Tool error

Tool execution failure 应作为 observation 返回模型。

## Model error

区分 tool error 和 provider error。

provider error 可终止 run，并给出清晰错误。

## Mock tests

先用 Fake / Mock Model 测：

1. 直接回答
2. read_file → final answer
3. 多轮 tool call
4. tool error 后修正
5. max_steps

Mock 通过后，再做一个最小真实 API smoke test。

## 本阶段禁止

不要：

- planner
- context compact
- subagent
- memory
- CLI 美化
- 自动进入 Phase 04

完成后停止。
