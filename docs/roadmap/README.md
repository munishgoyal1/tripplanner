# Roadmap

The roadmap contains possible future work, not approved implementation scope.

- [`FUTURE_FEATURES.md`](FUTURE_FEATURES.md): consolidated candidate outcomes,
  grouped by likely value and maturity.
- [`DEFERRED_DECISIONS.md`](DEFERRED_DECISIONS.md): choices deliberately postponed
  until a stated observation or trigger occurs.
- [`LLM_EFFICIENCY_BACKLOG.md`](LLM_EFFICIENCY_BACKLOG.md): deferred changes that
   reduce planning latency and model/provider cost without changing product scope.

## How it is used

1. Capture a meaningful future candidate here without changing current behavior.
2. Do not implement it merely because it appears in the roadmap.
3. When the owner selects an outcome, move its bounded scope into
   `docs/feature-briefs/NEXT_INCREMENT.md` or a numbered feature brief.
4. After implementation, update `docs/REQUIREMENTS.md` and remove or revise the
   roadmap candidate so it no longer describes shipped work as future work.

The roadmap answers "what might be next." Requirements answer "what is true now."
