# KC auditor calibration: five frozen baseline tasks

All five audits have a technically valid selected JSON. Four original outputs passed; 7D21DC needed one separate correction attempt. The original output remains unchanged.

| Task | Selected output | Match | Uncertain | Issues | Blocking issues |
|---|---|---:|---:|---:|---:|
| 7D21DC | attempts/7D21DC-a02.json | 4 | 0 | 1 | 0 |
| B948D4 | raw/B948D4.json | 2 | 0 | 0 | 0 |
| F2A2EB | raw/F2A2EB.json | 7 | 0 | 1 | 0 |
| 0063ED | raw/0063ED.json | 6 | 1 | 2 | 0 |
| eFF32e | raw/eFF32e.json | 9 | 1 | 3 | 0 |

## Execution and provenance

Each task used a fresh child agent via collaboration.spawn_agent with fork_turns=none and no model override. The correction used another fresh child. The first three tasks ran sequentially; the last two overlapped after root explicitly authorized parallel execution. Each auditor was instructed to read only its frozen request and listed images, using view_image for each image. The coordinator performed no semantic audit or semantic corrections.

Exact spawn messages, agent identifiers, input paths and SHA-256 values, timestamps, and output hashes are in executions/. Validator commands, exit codes and captured output are in validation/. summary.json records actual selected and raw hashes.

## Format finding

7D21DC used an absolute image path in evidence. The frozen validator requires image:assets/03325580d6a0dfa1afcc5fd2.png. Its raw output failed; the fresh correcting auditor wrote attempts/7D21DC-a02.json, which passed. No other output needed a correction attempt. Requests and criteria were not changed.

## Limits

These are five known baseline cases and one audit per case. Technical passing verifies schema, allowed references and literal quotes; it does not establish mathematical correctness, expert agreement, catalog quality, stability, or student benefit. Issues are auditor findings requiring review, not confirmed errors. No prior catalog, solution, prompt, or bank material was modified. No extension-150 author or audit run was started by this coordinator.

The 28 match and 2 uncertain decisions are outputs of these auditors, not an accuracy score. Total issues: 7. See the selected JSON for actual rationales and evidence; this administrative summary does not adjudicate them.
