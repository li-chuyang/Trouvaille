# Phase 00 — Architecture

## 目标

只做调研和架构设计。

不要实现正式业务代码。

## 要做

1. 阅读：
   - `AGENTS.md`
   - `CODEX_TASK_MVP.md`

2. 检查当前项目状态。

3. 快速查看：
   - `../ref/mini-swe-agent`
   - `../ref/learn-claude-code`

4. 必要时再看 Aider，不要全面研究。

5. 比较：
   - Agent Loop
   - Model
   - Tool Calling / Dispatch
   - Messages
   - Stop Condition
   - Environment / Workspace

## 输出

给我：

1. 推荐最小架构
2. 推荐文件树
3. 各模块职责
4. Reference mapping
5. 第一版明确不做什么
6. 最多 3~5 个风险点

## 设计要求

保持简单。

不要为了“工程化”引入：

- Factory
- EventBus
- Middleware Pipeline
- 复杂 DI
- 多层 Provider Registry

除非确实必要。

## 本阶段禁止

不要：

- 创建大量正式源码
- 安装大量依赖
- 实现 Agent Loop
- 实现 Tool
- 实现 CLI
- 自动进入 Phase 01

完成后停止。
