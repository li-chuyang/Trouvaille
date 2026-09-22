# Phase 09 — Verification Loop

## Goal
Turn verification from an optional behavior the model may choose into an explicit Coding Agent capability.

The agent should have a clear way to inspect its changes and verify them before declaring a coding task complete.

## Required work

1. Add a lightweight verification component/policy separate from the core tool implementations.
2. When files were modified, gather relevant verification evidence before successful completion where practical.
3. Verification should be based on the repository and task, using available signals such as:
   - `git diff`;
   - focused tests;
   - existing project test commands;
   - syntax/import checks;
   - lint/type/build commands only when already available and appropriate.
4. Do not blindly run every possible command. Prefer focused, bounded verification.
5. Feed failed verification results back into the Agent Loop as observations so the model can correct its work.
6. Record verification attempts and final verification status in `TaskState` and trajectory.
7. The final answer should clearly distinguish:
   - what was changed;
   - what was actually verified;
   - what could not be verified.
8. Verification failures must not be silently reported as success.
9. Preserve explicit stop/max-step limits so repeated verification/correction cannot loop forever.

## Tests
Add tests that verify at least:

- modified code triggers the verification path;
- a passing verification can finish successfully;
- a failing verification is returned to the agent for another step;
- repeated failure respects max-step / retry limits;
- unchanged/read-only tasks do not force unnecessary test execution;
- final result records what was and was not verified.

Use controlled fixture repositories and fake/mock models where possible.

## Non-goals
Do **not** add in this phase:

- Docker/sandbox infrastructure;
- CI service integration;
- automatic deployment;
- security auditing;
- external code review agents;
- multi-agent reviewer architecture;
- major CLI redesign.

## Completion report
After implementation, explain:

- when verification is triggered;
- how verification commands are selected;
- how failures return to the agent;
- how infinite retry is prevented;
- how final answers represent verification evidence;
- what tests were added and their results.

Stop after Phase 09. Do not start later enhancements automatically.
