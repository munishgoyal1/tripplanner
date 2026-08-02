# Feature Briefs

Feature briefs turn one approved product outcome into bounded implementation work.
They sit between broad intent and code: each brief states the user problem, scope,
non-goals, acceptance criteria, affected capability IDs, validation, and unresolved
owner decisions.

## Files

- [`NEXT_INCREMENT.md`](NEXT_INCREMENT.md): reusable owner-editable intake for the
  next coherent milestone. It is a draft until scope and approval are explicit.
- [`FEATURE_BRIEF_TEMPLATE.md`](FEATURE_BRIEF_TEMPLATE.md): full structure used to
  normalize a selected increment.
- Numbered briefs: scoped work records. Their document-control status says whether
  each is active, shipped, or superseded.

## Lifecycle

1. The owner raises a need directly or selects one candidate from `docs/roadmap/`.
2. Record the smallest coherent outcome in `NEXT_INCREMENT.md`.
3. Resolve material choices and create or update one numbered brief.
4. Implement only the approved scope and validate its acceptance criteria.
5. Update canonical requirements, product, architecture, or operations documents
   when current truth changes.
6. Mark the brief shipped or superseded; do not use it as a second current baseline.

A feature brief authorizes work only when its scope is owner-approved. Merely
existing in this folder does not approve implementation.
