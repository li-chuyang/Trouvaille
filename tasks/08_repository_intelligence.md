# Phase 08 — Repository Intelligence & Retrieval

## Goal
Give the Coding Agent a lightweight understanding of a repository so it can locate relevant code more efficiently than repeatedly exploring only through raw `list_files`, `search`, and `read_file` calls.

This phase should remain lightweight and understandable. Start with Python repositories; do not build a general code-search platform.

## Required work

1. Add a repository-intelligence component separate from the Agent Loop.
2. Build a lightweight repository snapshot containing useful structural information such as:
   - project file tree;
   - Python modules;
   - classes;
   - functions / methods;
   - imports;
   - test files where identifiable.
3. Prefer Python standard-library `ast` for the first implementation unless there is a concrete reason to add another parser.
4. Add a simple retrieval/ranking mechanism that can select repository items relevant to the user's task.
5. Ranking may use simple signals such as:
   - filename/path match;
   - symbol-name match;
   - task keyword overlap;
   - import relationships;
   - source/test naming relationships.
6. Produce a compact repository context representation that can be supplied to the model under the existing context budget.
7. Keep existing explicit tools (`search`, `read_file`, etc.). Repository intelligence should help the agent decide where to look; it must not replace normal file inspection.
8. Respect ignored/generated/hidden content where practical. Do not index `.venv`, `.git`, trajectory files, caches, or other obvious noise.
9. Keep the implementation deterministic and inspectable. The user should be able to print or inspect the generated repo summary during development.

## Tests
Add tests that verify at least:

- symbols are extracted correctly from small Python fixtures;
- ignored/noisy directories are skipped;
- a task mentioning a known file/symbol ranks it highly;
- relevant source/test relationships can be recovered in simple cases;
- generated repository context is bounded and deterministic;
- existing Agent behavior still works when repository intelligence is disabled.

## Non-goals
Do **not** add in this phase:

- embeddings or vector databases;
- Tree-sitter unless the standard-library approach is demonstrably insufficient;
- graph databases;
- full static call-graph analysis;
- language-server integration;
- external documentation/web retrieval;
- cross-task memory;
- subagents;
- major CLI redesign.

## Completion report
After implementation, explain:

- what repository information is extracted;
- how ranking works;
- how repository context reaches the model;
- how it fits within context management;
- what information is deliberately excluded;
- what limitations exist;
- what tests were added and their results.

Stop after Phase 08. Do not begin Phase 09 automatically.
