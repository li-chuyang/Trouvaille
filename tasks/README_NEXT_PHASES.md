# Coding Agent — Next Foundation Phases

The current MVP is complete. These four phases add only the next foundation layer; they intentionally do not define long-term memory, advanced RAG, subagents, sandboxing, or other later enhancements.

Recommended order:

1. `06_task_state.md` — add explicit working state for one task.
2. `07_context_management.md` — control what the model sees during long runs and preserve important state through compaction.
3. `08_repository_intelligence.md` — understand and retrieve relevant repository structure/code.
4. `09_verification.md` — make code verification an explicit completion loop.

Rationale for the order: explicit task state gives context management a stable set of important facts to preserve; repository context can then use the established context budget; verification can finally use task state plus repository knowledge to track changes and choose focused checks.

Execute one phase at a time. After each phase, review the implementation and stop before moving on.
