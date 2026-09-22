# Phase 06 — Explicit Task State

## Goal
Add a small explicit working-state layer for a running task so important facts are not represented only implicitly inside chat messages.

This is **working state for one run**, not long-term memory and not a heavy planner.

## Required work

1. Introduce a compact `TaskState` (or equivalent) owned by the running agent/task.
2. Keep only useful operational fields. Candidate fields include:
   - original goal;
   - current status;
   - important findings;
   - files inspected;
   - files modified;
   - commands/tests executed;
   - known failures/errors;
   - unresolved items / next actions.
3. Update state from actual tool/model events rather than duplicating arbitrary chat text.
4. Make state available to trajectory/debug output.
5. State updates must remain simple and understandable; avoid creating a generic workflow/state-machine framework.
6. Do not require the model to emit a complex schema on every step. Use deterministic updates where possible and model-written state only where clearly necessary.

## Tests
Add local tests that verify at least:

- inspected and modified files are tracked;
- command/test outcomes are recorded;
- errors can be represented without crashing the run;
- state is reset between independent tasks;
- state appears correctly in trajectory/debug information;
- existing Agent behavior remains unchanged when no additional state information is needed.

## Non-goals
Do **not** add in this phase:

- cross-task/long-term memory;
- a full planner or DAG workflow;
- context compaction;
- repository indexing;
- multi-agent task delegation;
- issue tracker integration;
- major CLI redesign.

## Completion report
After implementation, explain:

- what fields exist in task state;
- who updates each field;
- how it differs from messages;
- how it differs from trajectory;
- what tests were added and their results.

Stop after Phase 06. Do not begin Phase 07 automatically.
