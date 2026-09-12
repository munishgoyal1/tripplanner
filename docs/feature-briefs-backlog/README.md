# Feature Briefs

Feature briefs turn one approved product outcome into bounded implementation work.
They sit between broad intent and code: each brief states the user problem, scope,
non-goals, acceptance criteria, affected capability IDs, validation, and unresolved
owner decisions.

When every approved acceptance criterion is implemented, validated, and reflected in
the canonical docs, move the complete brief to [`../implemented/`](../implemented/README.md)
in the same completion commit and mark it `Shipped` or `Implemented`. Drafts,
partial foundations, pending UX choices, and briefs with outstanding criteria remain
in this backlog.

## Files

- [`009-booking-readiness.md`](009-booking-readiness.md): budget-constrained
  selections, saved alternatives, explicit readiness and external handoffs;
  provider feasibility and implementation validation remain pending.
- [`NEXT_INCREMENT.md`](NEXT_INCREMENT.md): reusable owner-editable intake for the
  next coherent milestone. It is a draft until scope and approval are explicit.
- [`FEATURE_BRIEF_TEMPLATE.md`](FEATURE_BRIEF_TEMPLATE.md): full structure used to
  normalize a selected increment.
- Numbered briefs: scoped work records. Their document-control status says whether
  each is active, shipped, or superseded.

**Brief numbers are unique keys.** Take the next unused number; never reuse one,
even for unrelated work, because "brief 004" has to name exactly one document.
Two collisions predate this rule and are left for the owner to renumber, since
the IDs have been cited outside the repository: `001-assistant-led-itinerary` /
`001-live-travel-availability`, and `004-auto-validation-harness` /
`004-item-comparison-budget-what-if`.

## Every feature starts here

A brief is required before code for a new capability, or a material change to
one — see [`../development/agent-workflow.md`](../development/agent-workflow.md).
Bug fixes, behaviour-preserving refactors, and doc-only changes do not need one.

The **acceptance criteria** and **validation matrix** carry more weight than they
used to. The complete test suites no longer run in the lane gates, so the brief is
the written record of what "done" meant — and it is what a later session reads
when one of these tests fails months from now and nobody remembers what it was
protecting. Write both so they survive that conversation.

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
