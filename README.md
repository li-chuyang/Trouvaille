# my-coding-agent

一个最小但完整的 CLI Coding Agent MVP。用户给出任务后，项目自己的 Agent Loop 调用模型、执行本地工具、把结果交回模型，直到得到回答或达到步数上限。

## 为什么自己实现 Agent Core

项目的目标是能看清并解释每一步：模型何时被调用、工具如何分发、结果怎样回填、何时停止。因此核心循环在本项目中显式实现；OpenAI SDK 只负责模型请求，没有使用外部 Agent runtime。

## 架构

```text
CLI → Conversation → Agent Loop → Model interface → OpenAI Responses API
                      ↓
                   Tool registry → Workspace → 文件 / shell / Git
                      ↓
                   Tool result → Messages → 下一次模型调用
                      ↓
                   Task State（本次任务的操作事实）
                      ↓
                   JSON trajectory
```

`conversation.py` 在一次 CLI 启动期间保存完整对话消息；`agent.py` 负责一次用户请求的循环和停止条件；`messages.py` 定义项目内部消息；`model.py` 把内部消息转换成 OpenAI 请求，并将响应归一化；`tools.py` 提供工具定义与分发；`workspace.py` 管理文件路径；`task_state.py` 记录本次任务已读取或修改的文件、命令结果及错误；`cli.py` 只处理输入和展示；`trajectory.py` 保存运行记录。每次 CLI 输入仍是独立的 Run，Task State 每次重置；同一次交互启动的后续 Run 会看到前面 Run 的 user、assistant 和工具消息。

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

文件工具使用相对 workspace root 的路径，并在解析符号链接后检查路径仍在 root 内。`shell` 的工作目录设为 root，并有超时，但它不是沙箱。

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
uv run my-agent --help
uv run my-agent
```

在 `User >` 输入任务；同一次启动中连续输入的任务共享完整对话历史，输入 `exit` 或 `quit` 退出。退出后这份内存历史消失，新启动从空对话开始。也可以指定 workspace 并运行单次任务：

```bash
uv run my-agent --workspace /path/to/workspace --max-steps 10 --task "描述这个项目"
```

CLI 显示 step、工具调用与结果、最终回答。每个 Run 的 JSON 记录单独写到 `<workspace>/.agentcore/trajectories/`，只记录本次 Run 的模型响应、工具调用与结果、状态和最终回答，不重复保存此前 Run 的步骤；记录可能包含任务文件内容，请按本地数据处理。

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

当前只有 OpenAI provider；没有权限审批或进程沙箱，`shell` 可以访问 workspace 以外的路径。`git_diff` 只显示已跟踪文件的未暂存改动。对话历史只在当前 CLI 进程内存在，不支持跨进程恢复；完整历史会不断增长，目前没有上下文压缩或 token 预算管理。也没有长期记忆、planner、subagent、Web UI 或 IDE 扩展。后续增强需单独设计与确认。
