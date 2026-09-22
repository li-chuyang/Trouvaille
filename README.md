# my-coding-agent

A small coding agent with an explicit Agent Loop and an OpenAI model adapter.

## Run

From this project directory:

```bash
uv sync
uv run my-agent --help
uv run my-agent
```

Set `OPENAI_API_KEY` and `OPENAI_MODEL` in the environment or in a local `.env` file before starting. The local `.env` is ignored by Git. Type a task at `User >`; type `exit` or `quit` to leave.

To run one task against another workspace:

```bash
uv run my-agent --workspace /path/to/workspace --task "Describe this project"
```

Each task writes a JSON trajectory under `<workspace>/.agentcore/trajectories/`. The CLI uses plain text while its visual design is pending. File tools stay within the selected workspace; the shell tool starts there but is not a sandbox.
