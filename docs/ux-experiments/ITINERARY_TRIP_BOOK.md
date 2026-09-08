# Experiment: Execution-ready Trip Book

## Meta

- Branch: not retained; current implementation work uses a sandbox
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

- `frontend/labs/lab-5-itinerary-trip-book.html`
- `frontend/labs/src/itinerary-trip-book/main.tsx`
- `frontend/labs/src/itinerary-trip-book/TripBookMap.tsx`
- `frontend/labs/src/catalog/main.tsx`
- `frontend/labs/vite.config.ts`

The Lab uses one realistic eight-day London family-trip fixture across all
variants. It previews contents, a trip brief, trip and day maps, an executable
day, essentials and help, a document wallet, and optional place context in an
A4-like frame.

Map snapshots are a separate control from the three structures, because whether
the packet draws its route is independent of how the packet is ordered. All
three structures accept all three map settings.

Non-goals:

- No production UI, API, export, or persistence changes
- No travel-document upload, extraction, storage, access, or retention design
  (superseded 6-Aug-2026 for the product, not for this Lab: see
  [`TRAVEL_DOCUMENTS.md`](TRAVEL_DOCUMENTS.md))
- No PDF attachment concatenation or email behavior
- No claim that fixture confirmations are real travel documents
- No provider map imagery, tile licensing, or static-map API contract; the Lab
  draws its own circuit so the packet can be judged before that choice

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

## Map Snapshot Setting

An orthogonal three-way control, applied on top of whichever structure is
selected:

- `No map` - the sequence is written but never drawn. Adds nothing.
- `Day circuit inset` (default) - every day spread carries its own numbered
  hotel-to-hotel circuit, using the same order and the same `H` and `1..n`
  markers as the agenda beside it. Costs no extra page.
- `Circuit inset + map pages` - adds a trip overview map with one marker per day
  and one full-page labelled day circuit. Costs two pages.

## Shared Information Architecture

1. Contents and document-readiness summary
2. Trip overview, departure actions, and family-specific guidance
3. Trip and day maps, when the map setting includes them
4. Daily itinerary with authoritative timing, transfers, addresses, confirmation
   references, weather band, expected spend, and booking states
5. Essentials and help: emergency, insurance, hotel, consulate and card-block
   numbers, local practicals, travelling party, and return logistics
6. Tickets, hotel vouchers, insurance, and visa or entry documents
7. Optional city, attraction, hotel, and family-interest guidance

## Completeness Audit

The Lab states, beside the preview, what the book carries and what it leaves out
on purpose, so the cut list is judged at the same time as the content.
Deliberately excluded: guidebook prose beyond one context page, alternatives that
were not chosen, live prices and provider terms that expire before departure,
full passport, card and policy numbers, and the original PDF attachments
themselves.

## Interaction Intent

- Primary workflow: switch between coherent packet variants and map settings,
  then inspect the same sections before saving a preferred direction.
- Secondary workflow: compare page count, personalization evidence, and missing
  document treatment without changing the underlying trip facts.
- Mobile behavior: horizontal section navigation and a responsive page preview;
  the artifact itself remains an A4/phone-PDF document rather than a mobile app.

## Test Scenarios

1. Open Contents and identify the only missing document group.
2. Open Day 3 and find start/end time, route burden, and every booking state.
3. Read Day 3's circuit map alone and recover the same stop order as the agenda.
4. Turn the map setting off, then to map pages, and judge whether either the loss
   or the two added pages is worth it.
5. Open Essentials and reach an emergency number without reading anything else.
6. Open Travel documents and locate the outbound e-ticket and UK ETA gap.
7. Open Place guide and identify the source class behind a family insight.
8. Read the completeness audit and name anything still missing for a real trip.
9. Repeat across A, B, and C and decide whether added pages improve confidence.
10. Save one option plus modification notes through the standard Lab handoff.

## Decision Criteria

- Today's executable plan or a named confirmation is reachable in under ten seconds.
- Missing travel documents are visible before export, not discovered in an appendix.
- Daily timing and booking state match the authoritative itinerary contract.
- The printed circuit shows the same order, numbering, and hotel endpoints as the
  agenda it sits beside, and stays readable in mono at A4 print size.
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
