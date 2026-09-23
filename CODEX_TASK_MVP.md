# CODEX_TASK_MVP.md

## Coding Agent MVP 总纲

本文件只定义 MVP 的最终目标和边界。

**不要一次性实现全部内容。**

开发必须严格按照 `tasks/` 下的 Phase 顺序执行。

每个阶段完成后停止，等待我确认。

---

## 最终目标

实现一个属于当前项目自己的、最小但完整的 Coding Agent。

核心流程：

```text
User Task
    ↓
Agent Loop
    ↓
Model
    ↓
Tool Call
    ↓
Tool Execution
    ↓
Observation
    ↓
Messages
    ↓
Next Step
    ↓
Final Answer
```

并提供一个基本 CLI。

---

## MVP 最终组件

### Core

- 自己实现 Agent Loop
- Conversation / Messages
- Model abstraction
- Tool abstraction / registry
- Tool dispatch
- Stop / max_steps
- Error handling

### Basic Tools

至少：

- list files
- read file
- write file
- edit file
- search
- shell
- git diff

### Workspace

- 所有文件操作基于 workspace root
- 防止明显 path traversal
- shell 默认在 workspace 中执行

### CLI

至少支持：

```bash
trouvaille
```

进入交互模式。

### Trace

至少记录或显示：

- step
- model response
- tool call
- tool arguments
- tool result
- final answer

---

## 第一版明确不做

- RAG
- vector database
- repository graph
- context compaction
- memory
- subagent
- multi-agent
- MCP ecosystem
- browser
- web UI
- IDE extension
- Docker sandbox
- SWE-bench
- 复杂 planner

---

## 开源参考原则

可以参考：

- mini-swe-agent
- learn-claude-code
- Aider

reference repositories 默认只读。

可以学习：

- 架构
- 接口
- tool schema
- CLI 组织
- model abstraction
- error handling

不要整体复制成熟项目。

---

## 开发阶段

```text
00 Architecture
      ↓
01 Skeleton
      ↓
02 Model + Tools
      ↓
03 Agent Loop
      ↓
04 CLI + Runtime
      ↓
05 Tests + Demo
```

每次只执行一个阶段。

**阶段完成后必须停止。**
