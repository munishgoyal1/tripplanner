# Evaluation and planning efficiency (2026-09-23)

Deferred, unapproved. EE-01 to EE-04 shipped on 2026-09-24 and are archived in
[`../implemented/evaluation-and-planning-efficiency.md`](../implemented/evaluation-and-planning-efficiency.md).
Evidence is data in [`corpus/evals/findings.json`](../../corpus/evals/findings.json),
rendered on `/evals` → Efficiency.

| ID | Item | Value | Effort | Payoff that makes it worth doing |
| --- | --- | --- | --- | --- |
| EE-05 | Run the corpus probes on every pull request | Medium | S | A zero-cost quality signal in under a second while the complete suites are suspended. |

Validation if selected: promote the probes into the audit rule registry with an
accepted baseline and prove a new occurrence on a committed corpus trip fails the
gate while existing occurrences do not.
