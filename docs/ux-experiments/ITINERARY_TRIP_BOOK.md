# Experiment: Execution-ready Trip Book

## Meta

- Branch: `agents/worker-1`
- Owner: Munish Goyal
- Date started: `2026-07-30`
- Date ended: pending
- Status: `testing`

## Hypothesis

A layered Trip Book will outperform both a dense operations binder and a
photo-led journey book. It should keep the live itinerary fast to scan while
placing confirmations, entry documents, and optional destination context in
predictable sections that remain useful as a printed packet or phone PDF.

The experiment is successful if a traveler can find today's plan or a named
confirmation in under ten seconds, understand what is missing before departure,
and distinguish verified facts from personalized suggestions.

## Scope

Changed Lab surfaces:

- `frontend/labs/itinerary-trip-book.html`
- `frontend/labs/src/itinerary-trip-book/main.tsx`
- `frontend/labs/src/catalog/main.tsx`
- `frontend/labs/vite.config.ts`

The Lab uses one realistic eight-day London family-trip fixture across all
variants. It previews contents, a trip brief, an executable day, a document
wallet, and optional place context in an A4-like frame.

Non-goals:

- No production UI, API, export, or persistence changes
- No travel-document upload, extraction, storage, access, or retention design
- No PDF attachment concatenation or email behavior
- No claim that fixture confirmations are real travel documents

## Variants

### A - Operations Binder

The shortest packet. Dense checklists, compact itinerary facts, restrained
imagery, and a document-first visual language optimize for printing and rapid
lookup. It risks feeling administrative and can suppress useful trip context.

### B - Layered Trip Book (recommended)

A concise trip-control opening, executable day spreads, and appendices for
confirmations and optional context. It keeps the operational path short without
forcing every useful detail into the daily agenda.

### C - Visual Journey Book

A photo-forward editorial packet with stronger destination context and a full
operational appendix. It can feel more memorable and family-friendly, but adds
pages and may slow document lookup.

## Shared Information Architecture

1. Contents and document-readiness summary
2. Trip overview, departure actions, and family-specific guidance
3. Daily itinerary with authoritative timing, transfers, and booking states
4. Tickets, hotel vouchers, insurance, and visa or entry documents
5. Optional city, attraction, hotel, and family-interest guidance

## Interaction Intent

- Primary workflow: switch between coherent packet variants, then inspect the
  same five sections before saving a preferred direction.
- Secondary workflow: compare page count, personalization evidence, and missing
  document treatment without changing the underlying trip facts.
- Mobile behavior: horizontal section navigation and a responsive page preview;
  the artifact itself remains an A4/phone-PDF document rather than a mobile app.

## Test Scenarios

1. Open Contents and identify the only missing document group.
2. Open Day 3 and find start/end time, route burden, and every booking state.
3. Open Travel documents and locate the outbound e-ticket and UK ETA gap.
4. Open Place guide and identify the source class behind a family insight.
5. Repeat across A, B, and C and decide whether added pages improve confidence.
6. Save one option plus modification notes through the standard Lab handoff.

## Decision Criteria

- Today's executable plan or a named confirmation is reachable in under ten seconds.
- Missing travel documents are visible before export, not discovered in an appendix.
- Daily timing and booking state match the authoritative itinerary contract.
- Personal insights name both preference evidence and a verified travel source.
- Optional context never obscures the operational trip path.
- The selected structure works as both a printed packet and a phone PDF.

## Production Boundary

A selected visual structure is not approval to add document storage. Production
work requires a separate contract for ownership, supported formats and sizes,
malware handling, encryption, access control, retention/deletion, redaction,
append ordering, and failure behavior during export. Existing itinerary HTML,
PDF, print, email, photo, map, and booking-state exports remain unchanged during
this experiment.

## Scorecard (1-5)

- Completion speed:
- Clarity:
- Cognitive load (higher is better/easier):
- Mobile/PDF usability:
- Document confidence:
- Personal relevance:

## Findings

- What worked: pending owner evaluation
- What failed: pending owner evaluation
- Surprises: pending owner evaluation

## Decision

- Decision: pending
- Working recommendation: `B - Layered Trip Book`
- Rationale: it best separates fast day execution from completeness evidence and
  optional enrichment while preserving one predictable packet.
- Next action: save the preferred Lab option and requested modifications; scope
  production contracts only after the owner separately approves implementation.
