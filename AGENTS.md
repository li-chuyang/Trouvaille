# AGENTS.md

## 1. 项目定位

当前目录 `my_coding_agent/` 是我自己的正式 Coding Agent 项目。

目标是先实现一个属于自己的、最小但完整、可运行、可继续扩展的 Coding Agent MVP，然后再做后续增强。

当前第一版重点：

- Agent Loop
- Model abstraction
- Messages / Conversation
- Tool system
- Workspace
- CLI
- Trajectory / logging
- 基本 error handling

当前不要追求复杂功能。

---

## 2. 当前工作区结构

当前 VS Code 打开的外层工作区是：

```text
codingagent_workspace/
├── my_coding_agent/          # 当前主项目
└── ref/                      # 只读参考源码
    ├── mini-swe-agent/
    ├── learn-claude-code/
    ├── aider/
    └── other repositories...
```

非常重要：

- `codingagent_workspace/` 只是 VS Code workspace root
- 它不是 Python project root
- 真正的 Python 项目是 `my_coding_agent/`

---

## 3. Python 环境与终端规则

主项目唯一的虚拟环境是：

```text
my_coding_agent/.venv/
```

外层 `codingagent_workspace/` 不应该创建 `.venv`。

`ref/` 下的仓库目前也不需要虚拟环境，因为它们主要用于源码阅读。

针对主项目执行 Python / uv / pytest / CLI 命令时，优先：

```bash
cd my_coding_agent
uv run ...
```

例如：

```bash
cd my_coding_agent
uv run python --version
uv run pytest
uv run trouvaille
```

如果从 workspace root 执行，则显式指定：

```bash
uv run --project my_coding_agent ...
```

不要从 `codingagent_workspace/` 根目录直接执行：

```bash
python ...
pip install ...
pytest
```

不要：

- 在 workspace root 创建新的 `.venv`
- 用系统 Python 替代主项目环境
- 用 `my_coding_agent/.venv` 给 `ref/` 下的项目安装依赖
- 自动给 reference repo 创建环境或安装依赖

---

## 4. 依赖管理

主项目使用 uv。

依赖优先通过：

```bash
uv add <package>
uv remove <package>
uv sync
uv run ...
```

管理。

不要优先使用裸 `pip install`。

项目依赖由：

```text
pyproject.toml
uv.lock
```

统一管理。

---

## 5. Reference repositories 规则

`../ref/` 下所有仓库默认视为只读参考。

可以：

- 阅读源码
- 搜索实现
- 跟踪调用链
- 比较架构
- 借鉴接口和设计思想

不要：

- 修改 reference repo
- 在 reference repo 中提交代码
- 删除 reference repo 文件
- 自动安装依赖
- 自动创建 `.venv`
- 整体复制大段源码
- 把 reference repo 当当前项目开发

如果确实需要运行某个 reference repo，先说明为什么。

---

## 6. 自己的 Coding Agent

本项目不能只是：

- Aider 改名
- mini-swe-agent 直接复制
- LangGraph Agent 简单封装
- 一个只调用模型 API 的薄 wrapper

允许参考成熟项目，但当前项目必须有自己的核心 Agent 实现。

需要自己实现并能解释：

```text
User Task
    ↓
Agent Loop
    ↓
Model
    ↓
Tool Call
    ↓
Tool Dispatch
    ↓
Tool Result / Observation
    ↓
Messages
    ↓
Next Model Step
```

---

## 7. LangGraph / LangChain 使用边界

MVP 阶段不要使用 LangGraph 或 LangChain Agent runtime 来负责核心 Agent Loop。

意思是：

以下核心逻辑必须在当前项目中显式实现：

- while / step loop
- model invocation
- tool-call parsing
- tool dispatch
- observation 回填
- stop condition
- max steps

可以正常使用通用基础库：

- provider SDK
- Pydantic
- Rich
- Typer / Click
- python-dotenv

以后外围能力是否使用 LangGraph，再单独讨论。

---

## 8. 分阶段开发

开发按以下阶段进行：

```text
Phase 00  Architecture
Phase 01  Skeleton
Phase 02  Model + Tools
Phase 03  Agent Loop
Phase 04  CLI + Runtime
Phase 05  Tests + Demo
```

对应：

```text
CODEX_TASK_MVP.md
tasks/00_architecture.md
tasks/01_skeleton.md
tasks/02_tools_model.md
tasks/03_agent_loop.md
tasks/04_cli_runtime.md
tasks/05_tests_demo.md
```

一次只执行一个 Phase。

每个 Phase 完成后停止，等待我确认。

不要自动进入下一阶段。

---

## 9. Reference 使用优先级

### mini-swe-agent

重点参考：

- 极简 Agent Loop
- Model / Environment separation
- trajectory
- minimal architecture

### learn-claude-code

重点参考：

- tool calling
- tool result 回填
- incremental harness design
- CLI / permission / task 的设计思路

### Aider

MVP 阶段只在确有必要时参考：

- CLI UX
- file editing
- git integration
- model abstraction

不要为了第一版深入研究整个 Aider。

---

## 10. CLI 视觉设计规则

CLI 的视觉设计由我决定。

不要自行决定最终：

- Logo
- ASCII banner
- 字体颜色
- 主题色
- 分隔线风格
- prompt 符号
- tool-call 展示样式
- success / error 视觉风格
- spinner / panel 风格

MVP 阶段只需要保证：

- CLI 能正常交互
- Agent Core 与 CLI presentation 分离
- 后续可以独立替换视觉样式

CLI 视觉规范统一读取：

```text
CLI_DESIGN.md
```

当前 `CLI_DESIGN.md` 只是占位规范。

除非我明确给出设计，不要自行做复杂美化。

---

## 11. 开发原则

优先：

```text
理解问题
→ 查看 reference
→ 设计最小方案
→ 实现
→ 测试
→ 再继续
```

不要：

```text
先生成大量代码
→ 再试图理解
```

如果设计明显影响后续架构，先讨论再实现。

---

## 12. MVP Scope

暂时不做：

- RAG
- vector database
- repository graph
- context compact
- memory
- subagent system
- multi-agent
- browser
- web UI
- IDE extension
- Docker sandbox
- SWE-bench
- 复杂 planner

这些全部属于第二阶段。

---

## 13. 测试与验证

每完成一个主要阶段，都要做最基本验证。

所有主项目测试命令必须：

- 在 `my_coding_agent/` 下执行，或
- 显式使用 `uv run --project my_coding_agent ...`

执行前注意当前 `pwd`。

---

## 14. Git 安全

外层 workspace 不是主项目 Git repo。

Git 操作只针对：

```text
my_coding_agent/
```

不要：

- 在外层 workspace 做会波及多个 repo 的 Git 操作
- 把 `ref/` 加进主项目 Git
- 删除 reference repo 的 `.git`
- 把 reference repo 一起提交

---

## 15. 和我交流的方式

使用中文解释。

代码和技术术语可以保留英文。

当参考开源项目时，请明确告诉我：

1. 看了哪个文件 / 模块
2. 它解决什么问题
3. 我们借鉴什么
4. 哪些部分不照搬
5. 为什么我们这样设计

重要设计不要直接替我决定。

---

## 16. 当前最高优先级

当前最高优先级是：

> 先做出一个结构清楚、能运行、我能理解并解释的 Coding Agent MVP。

在此之前：

- 不要过早优化
- 不要堆 feature
- 不要引入复杂框架
- 不要扩大 scope
