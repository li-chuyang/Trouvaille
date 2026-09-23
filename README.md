# Trouvaille

一个最小但完整的 CLI Coding Agent MVP。用户给出任务后，项目自己的 Agent Loop 调用模型、执行本地工具、把结果交回模型，直到得到回答或达到步数上限。

## 为什么自己实现 Agent Core

项目的目标是能看清并解释每一步：模型何时被调用、工具如何分发、结果怎样回填、何时停止。因此核心循环在本项目中显式实现；OpenAI SDK 只负责模型请求，没有使用外部 Agent runtime。

## 架构

```text
CLI → Conversation → Agent Loop + Lifecycle Hooks → Context Manager → Model interface → OpenAI Responses API
        ↕
    SessionStore → .agentcore/sessions/
                      ↓
                   Tool registry → Workspace → 文件 / shell / Git
                      ↓
                   Tool result → Messages → 下一次模型调用
                      ↓
                   Task State（本次任务的操作事实）
                      ↓
                   JSON trajectory
```

`conversation.py` 在一次 CLI 启动期间保存完整对话消息；`session.py` 将 raw conversation history 持久化到当前 workspace；`agent.py` 负责一次用户请求的循环和停止条件；`lifecycle.py` 提供同步生命周期扩展点；`context.py` 通过 `before_model` 测量临时上下文、缩减大型工具结果并摘要较旧的完整 Run；`messages.py` 定义项目内部消息及 Session codec；`model.py` 把内部消息转换成 OpenAI 请求，并将响应归一化；`tools.py` 提供工具定义与分发；`workspace.py` 管理文件路径；`task_state.py` 记录本次任务操作事实；`cli.py` 处理输入和展示；`trajectory.py` 保存运行记录。每次 CLI 输入仍是独立的 Run，Task State 每次重置；同一次交互启动和显式恢复的后续 Run 会看到前面 Run 的 user、assistant 和工具消息。

Lifecycle Hook 按注册顺序同步执行。一次工具步骤的顺序是 `before_model → model → after_model → before_tool → tool（或明确阻止）→ after_tool`，Run 结束时执行一次 `after_run`。`before_model` 只变换本次模型调用的临时消息视图，不改写原始 Conversation；`before_tool` 可以产生正常的失败 `ToolResult` 来阻止底层工具。`AgentEvent / on_event` 继续负责 CLI/UI 观察通知，Lifecycle Hook 则是可以参与执行决策的扩展点。

Context Manager 的顺序是 `预算测量 → ToolResult micro-compaction → 较旧完整 Run 的结构化摘要 → 重新测量`。Conversation 和 Run 保存的是完整 raw history，模型收到的是临时 model-facing context；缩减不会改写 trajectory。预算估算和摘要缓存目前只在本次进程内，持久 Session 和模型专用 tokenizer 留待后续阶段。

## 支持的工具

| 工具 | 作用 |
| --- | --- |
| `list_files` | 列出目录内容 |
| `read_file` | 读取 UTF-8 文件 |
| `write_file` | 写入 UTF-8 文件 |
| `edit_file` | 替换恰好出现一次的文本 |
| `search` | 在文件中搜索字面字符串 |
| `shell` | 在 workspace 目录执行命令 |
| `git_diff` | 查看未暂存的 Git 改动 |

原生文件工具通过 `AgentWorkspaceView` 访问 workspace。路径会先解析为 canonical path，再分类为 PROJECT、INTERNAL 或 OUTSIDE；工具只允许 PROJECT 资源。因此 `.agentcore/` 及指向它或 workspace 外部的符号链接不会出现在 listing/search 中，也不能被文件工具直接读写。trajectory writer 使用独立的 Workspace internal API，仍将记录写入 `.agentcore/trajectories/`。

`shell` 通过 `LocalExecutionBackend` 在 workspace root 中执行并保留原有超时和输出语义。该 backend 不提供操作系统级隔离，所以 shell 命令仍可能读取 `.agentcore/` 或 workspace 外部资源；后续需要由真正的 sandbox execution backend 解决。

## 安装与配置

需要 Python 3.12+ 和 uv。在 `my_coding_agent/` 项目目录运行：

```bash
uv sync
```

在环境变量或项目目录的 `.env` 中设置：

```text
OPENAI_API_KEY=你的 API key
OPENAI_MODEL=你可用的模型 ID
```

`.env` 已被 Git 忽略。不要把真实密钥写入仓库文件。

## 使用

```bash
uv run trouvaille --help
uv run trouvaille
uv run trouvaille --resume
uv run trouvaille --resume <session-id>
uv run trouvaille --continue
```

在 `User >` 输入任务；同一次启动中连续输入的任务共享完整对话历史。普通启动总是创建新的空 Session；只有 `--resume` 或 `--continue` 会恢复历史。无参数的 `--resume` 打开当前 workspace 的交互式 picker，`--resume <session-id>` 精确恢复指定 Session，`--continue` 恢复最近更新的 Session。Session 保存在 `<workspace>/.agentcore/sessions/`，启动后直接 `exit` 不会生成空文件。

输入 `exit` 或 `quit` 退出。也可以指定 workspace 并运行单次任务：

```bash
uv run trouvaille --workspace /path/to/workspace --max-steps 10 --task "描述这个项目"
```

CLI 显示 step、工具调用与结果、最终回答。每个 Run 的 JSON 记录单独写到 `<workspace>/.agentcore/trajectories/`，只记录本次 Run 的模型响应、工具调用与结果、状态和最终回答，不重复保存此前 Run 的步骤；记录可能包含任务文件内容，请按本地数据处理。

`--task` 是一次性 Run，只写 trajectory，不创建或更新 Session，也不能与 `--resume`、`--continue` 同时使用。Session 使用同目录临时文件和原子替换保存；多个进程同时修改同一个 Session 时不保证自动合并。

## Demo 与测试

`demo_workspace/` 是独立样例：一个 `add` 函数有错误，测试期望正确加法。以下命令复制样例到项目内的临时目录，建立临时 Git 基线，再让真实模型查看文件、修复、运行测试、查看 diff 并回答；临时目录在运行结束后清理。

```bash
uv run python demo/run_demo.py
```

Demo 需要上述 API 配置，会产生真实模型请求。无需 API 的本地测试：

```bash
uv run python -m unittest discover -v
```

## 当前限制与后续方向

当前只有 OpenAI provider；没有权限审批或进程沙箱，`LocalExecutionBackend` 下的 `shell` 可以访问 `.agentcore/` 和 workspace 以外的路径。`git_diff` 只显示已跟踪文件的未暂存改动。对话历史只在当前 CLI 进程内存在，不支持跨进程恢复；完整历史会不断增长，目前没有上下文压缩或 token 预算管理。也没有长期记忆、planner、subagent、Web UI 或 IDE 扩展。后续增强需单独设计与确认。
