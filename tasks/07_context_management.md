# Phase 07 — Context Management

## Goal
Add a small, explicit context-management layer so long agent runs do not grow `messages` without control.

The goal is **not** to build memory or RAG. This phase only answers:

> For the current model call, which parts of the current run should be sent to the model, and how do we keep that context within a reasonable budget?

## Required work

1. Add a dedicated context-management component instead of putting compaction logic directly into `agent.py`.
2. Track the approximate size of the model context. Prefer the provider tokenizer if already available; otherwise use a simple, documented approximation for the MVP.
3. Keep recent user / assistant / tool interactions available verbatim.
4. When the configured threshold is exceeded, compact older history into a concise summary.
5. Preserve important information from the current `TaskState`, including goal, important findings, modified files, relevant errors, verification history, and unresolved work.
6. Large tool outputs must be bounded or truncated before they can dominate the next model request.
7. The complete run history must still remain available to trajectory/logging; compaction must only change the context sent to the model, not destroy the historical record.
8. Make thresholds configurable with simple project configuration or constants; do not introduce a large configuration framework.

## Tests
Add local tests that verify at least:

- short runs are not compacted unnecessarily;
- context over the threshold is compacted;
- recent messages remain available;
- important `TaskState` information survives compaction;
- oversized tool output is bounded;
- trajectory/history still contains the original run information;
- the Agent Loop continues correctly after compaction.

Use fake/mock models for deterministic tests. Do not require a real API for unit tests.

## Non-goals
Do **not** add in this phase:

- cross-task memory;
- vector database / embeddings;
- repository indexing;
- subagents;
- planner;
- external document RAG;
- major CLI redesign.

## Completion report
After implementation, explain:

- where full history is stored;
- what is sent to the model;
- what is kept verbatim;
- what is summarized/truncated;
- when compaction triggers;
- how `TaskState`, messages, and trajectory differ;
- what tests were added and their results.

Stop after Phase 07. Do not begin Phase 08 automatically.
