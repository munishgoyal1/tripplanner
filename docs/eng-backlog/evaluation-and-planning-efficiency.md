# Evaluation and planning efficiency (2026-09-23)

Deferred, unapproved. Recorded from the offline evaluation behind the owner `/evals`
console. The evidence for each item (profiles, prevalence counts, examples) is
data in [`corpus/evals/findings.json`](../../corpus/evals/findings.json) and is
rendered on `/evals` → Efficiency; it is not repeated here. Items are ranked by
value, and the list is deliberately short: only items with a measured payoff are
included.

| ID | Item | Value | Effort | Payoff that makes it worth doing |
| --- | --- | --- | --- | --- |
| EE-01 | Stop attaching the whole 13 MB place cache to every corpus record | Very high | S | About 95% of incremental-audit time goes to serialising and hashing that cache (the uncached path audits 391 records in 70 s), and audit state would grow to about 7 GB per full run. The same payload blocks the judge. |
| EE-02 | One stop classifier and a post-lookup identity check before any paid Places call | High | M | 11.3% of cached resolutions share no word with the stop name. Paid lookups of times and activity labels stop, and wrong pins disappear. |
| EE-03 | Deterministic save-time plan normaliser instead of prompt rules and repair turns | High | M | Removes the ordering, checkout, summary and placeholder defect classes, and cuts repair rounds on a 5.4-minute median build. |
| EE-04 | Self-describing paid corpus (request, expectations, producer, correct date span) | Medium-high | S | Lets the ₹7,469 corpus be judged and compared indefinitely without paid regeneration. |
| EE-05 | Run the corpus probes on every pull request | Medium | S | Gives a zero-cost quality signal in under a second while the complete suites are suspended. |

Validation for any selected item: the probe counts and the audit wall-clock time
on the committed corpus, before and after, from `scripts/dev/owner_evals.py
publish` and `scripts/dev/trip_audit.py`, with no paid call.
