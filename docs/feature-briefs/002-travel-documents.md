# 002 - Travel documents: bookings, traveler IDs, and entry permissions

## Document control

| Field | Value |
|---|---|
| Brief ID | `002` |
| Status | Retention decided - UX direction in evaluation |
| Owner | Munish Goyal |
| Created | 2026-08-06 |
| Updated | 2026-08-06 |
| Baseline | `docs/REQUIREMENTS.md` at `0e5ca20` |
| Target milestone | TBD |
| UX Lab | [Lab #20 - Travel documents](../ux-experiments/TRAVEL_DOCUMENTS.md) |
| Related capability IDs | `LIFE-01`, `LIFE-02`, `MEM-01`, `DATA-01`, `EXPORT-01`, `SAFE-01`, `PLAN-02` |

## One-sentence requirement

As the traveler, I need to attach booking confirmations and traveler identity
documents once, so that the planner can use real confirmation references, real
expiry dates, and real entry eligibility, and so that one exported document can
carry the whole trip.

## Owner intent captured

- Upload booking-related files: PDF, screenshots, text, Word documents.
- Upload passport, visa, and other identity documents.
- Use passport and visa expiry, date of birth, and nationality for planning
  insight and visa-free entry eligibility.
- Optionally include booking references and personal identity details in the
  itinerary export so one document serves the whole trip.
- Optionally remember identity and visa documents in the account for future trips.
- Save booking references against the trip.
- Provide a way to view, update, and delete uploaded documents.
- Keep the bookings flow separate from the identity documents flow.

## Owner decisions (6-Aug-2026)

These are settled. They are constraints on every option, not variables.

1. **Originals are never stored.** A file is read once, the fields that answer a
   planning question are extracted, and the file is discarded. There is no
   "keep the original" mode and no retention choice to present.
2. **The extracted fields are the reuse mechanism.** Because the fields persist on
   the account, the next trip is checked without asking for the same passport
   again. This answers the owner's own concern directly: reuse comes from the key
   information, never from a stored document.
3. **`.docx` is out of the first version.** Accepted inputs are PDF, JPEG, PNG,
   HEIC, and pasted text.

The consequences are worth stating, because they simplify the rest of this brief
considerably: there is no blob container to secure, no SAS issuance, no lifecycle
rule, no thumbnail pipeline, no download path, and no original-file access event.
A breach exposes a masked number and an expiry date rather than a scan of an
identity document.

## Critique of the proposal as stated

The intent is sound and matches the existing roadmap candidate
[Reservation Import and Trip Inbox](../roadmap/FUTURE_FEATURES.md). Five
corrections are recommended before implementation.

### 1. This is a risk-class change, not a feature increment

Today the product stores preferences and itineraries, and telemetry deliberately
excludes personal content (`SAFE-01`). Passport and visa scans for a whole family
turn one compromised session into identity-theft material. The feature is worth
building, but it must be designed as a small, deliberately boring vault rather
than as general file attachment.

**Recommendation:** extract-then-discard, with no option to keep the original.
Persist only the structured fields the planner actually uses.
*Owner decision, 6-Aug-2026: accepted, and tightened - there is no retain option
at all.*

The planner only needs these fields for every insight the owner described:

| Insight | Fields genuinely required |
|---|---|
| Passport validity for a trip | Issuing country, expiry date, holder |
| Six-month validity rule | Expiry date, return date |
| Visa-free eligibility | Issuing country, destination, trip dates |
| Visa validity for a trip | Entry type, valid-from, valid-to, destination |
| Age-based pricing and eligibility | Date of birth |

The passport number itself is required for none of them. It is useful only when
transcribing a booking form, so store it masked, reveal on explicit action, and
never place it in telemetry, model prompts, or share snapshots.

### 2. Three storage classes triples the security surface

Bookings, identity documents, and visa documents should be **one typed vault with
one permission, retention, audit, and deletion contract**, exposed as **two
flows**, exactly as the owner asked for at the interaction level:

- **Bookings** - trip-scoped, attached to an itinerary occurrence.
- **Traveler documents** - person-scoped, reusable across trips. Passport, visa,
  and the additional types below are types within this flow, not separate stores.

A visa is not an independent document class: it is an entry permission bound to a
passport, a destination, and a validity window. Modeling it as a type keeps
"which visa applies to this trip" answerable instead of requiring a manual join.

### 3. Bookings already have an owner in the data model

Itinerary stops already carry independent booked state (`/trip/stop/booked`,
`EB-FOCUS-001` occurrence identity). A booking confirmation must attach to the
exact occurrence (day plus stop position) and set that state, rather than
creating a second parallel list of bookings that can disagree with the itinerary.

### 4. Extraction must never write to the itinerary directly

Reuse the existing structured review pattern (`request_trip_input` card): extract,
show a prefilled review card with the source visible, and require explicit
confirmation. This matches the roadmap rule and the product rule that direct
mutations stay deterministic while model output stays proposal-only.

### 5. Eligibility must be grounded, never recalled

`src/tripplanner/tools/visa.py` already performs a grounded, sourced check.
Visa-free claims must come from that tool with its source shown and an explicit
"verify with the official mission" disclaimer. Deterministic checks that need no
model at all should be computed and explained instead:

- Passport expiry before or within six months of the return date.
- Visa validity window not covering the travel dates.
- Document expiring between booking and travel.
- A traveler on the trip with no passport record at all.

## Additional document types worth adding

Ranked by planning value against sensitivity.

| Type | Why it earns a place | Sensitivity |
|---|---|---|
| Travel insurance | Policy number and 24x7 assistance number are the single most useful things to have in a printed packet during disruption | Low |
| Vaccination or health certificate | Yellow fever proof is a legal entry condition for some destinations, so it belongs beside visa logic | Medium |
| Driving licence and International Driving Permit | Required for car rental; expiry affects the trip | Medium |
| Loyalty and travel programs | Frequent flyer, hotel status, rail pass; improves booking handoff quality | Low |
| Emergency contact and critical medical notes | Belongs in the offline packet; already partially modeled in `family_members` | Medium |

**Explicitly refused:** payment cards, bank details, tax identifiers, and any
document whose only use is payment. The product does not purchase anything
(`BOOK-01`), so it has no reason to hold payment credentials.

## Design

### Interaction model

Two entry points, one vault.

1. **Bookings** live where the booking lives. Attach from an itinerary stop, and
   from a compact `Add booking` action in the trip actions menu. After extraction
   and confirmation the stop shows a quiet confirmation chip; the reference is one
   click from the stop it belongs to.
2. **Traveler documents** live in Account settings as a `Travel documents`
   section, alongside Travel Profile and Privacy and data, because they are
   account-scoped and reused across trips. Each document is listed under the
   traveler it belongs to, using the existing `family_members` identity.
3. A trip-level `Documents` view answers only one question: *is this trip's
   paperwork ready?* It lists per traveler what is present, what expires too soon,
   and what is missing, and links back to the two flows above. It does not become
   a third store.

### Applying the existing taste rules

| Existing tenet | Application here |
|---|---|
| Read-only views render instantly from cache | Document lists render from stored fields only; there are no file bytes to fetch |
| Suggestions never disappear | Replacing an expired passport keeps the prior record visible as superseded until explicitly deleted |
| Information-rich but ordered | One row per document: type, traveler, expiry with a status tint, and one primary action |
| One clear primary action per item | Row action is `View`; update and delete live behind the row's overflow, so a destructive action is never the fastest click |
| Never overwrite user data | Extraction merges additively into an existing record and shows a field-level diff before saving |
| Settings has one owner | Travel documents is a section of the existing account sheet, not a new top-level command |
| Only panes scroll | The documents surface scrolls inside its pane; no new page-level scroll |
| Progress must be honest | Capture shows real states: reading, extracting, awaiting confirmation, saved, or failed with a reason - and says plainly that the file was discarded |

### Performance rules

- The file is held in memory for the duration of extraction and never written to
  durable storage; extraction streams its result, so the UI is never blocked by a
  model call.
- Every list and every check reads stored fields only. No view in this feature
  needs to fetch, decode, or render a document.

## Storage contract changes

### No binary storage

No blob container is provisioned, because no original file is kept. The uploaded
bytes exist only inside the request that extracts them and are released when that
request ends. This removes the entire class of work that document storage would
otherwise require: private containers, user-delegation SAS, `Content-Disposition`
hardening, lifecycle expiry rules, thumbnail generation, and download auditing.

The transfer itself still needs care: cap the request size, validate content type
by magic bytes before decoding, and never write the payload to a temporary file or
a log.

### Metadata

One new Cosmos container, partitioned by user identity:

| Container | Stores |
|---|---|
| `documents` | Extracted fields, booking linkage, and provenance. No file bytes, ever. |

Document shape, kept deliberately flat:

```text
id, user_id, scope ("traveler" | "trip"), trip_id?, traveler_key?,
type ("passport" | "visa" | "insurance" | "vaccination" | "licence" |
      "loyalty" | "booking"),
status ("ready" | "failed" | "superseded"),
fields { issuing_country, number_masked, expiry, date_of_birth, ... },
booking { provider, reference, occurrence_day, occurrence_index, amount, currency },
provenance { captured_at, source_kind ("pdf" | "image" | "text"), confidence,
             confirmed_by_user },
created_at, updated_at, revision
```

There is no `blob_path`. A record that cannot point at a file cannot leak one.

### Existing contracts touched

- Itinerary stop gains an optional booking reference pointer; mutations stay
  revision-guarded like every other trip write.
- `share.py::sanitize_plan` is an allowlist today, which is why identity data
  cannot leak through share links by accident. That allowlist must remain an
  allowlist, and this brief must not add any document field to it.
- `/account/privacy` must delete `documents` records. Without this, `clear_all_data`
  would report success while passport fields survive.
- `SAFE-01` currently claims six application containers are covered by the
  backup and recovery drill. Adding `documents` requires updating that evidence.

## Security requirements

- Identity documents require a signed-in account. Guest (`web-*`) identities may
  attach bookings only; a browser-local capability is not an acceptable owner for
  a passport.
- Validate content type by magic bytes, not by file extension or client-sent type.
- Reject SVG, HTML, and archives. Cap request size and per-account record count.
- The uploaded bytes are never persisted, never logged, and never written to a
  temporary file. Image EXIF and GPS data are discarded with the rest of the file.
- Document numbers are stored masked. The unmasked number is never stored, so it
  cannot be revealed later by any code path.
- Never include document fields in analytics, structured logs, share snapshots,
  or passive learning. Log document events by type and outcome only.
- Rate-limit uploads and extraction on the existing admission boundary.

## Export behavior

- Identity details are excluded from every export by default.
- Including them is an explicit per-export choice, and numbers stay masked unless
  the user separately chooses to reveal them.
- Public share links never include documents, references, or identity fields.
- Email delivery of an unmasked identity number requires a second confirmation,
  because email is not a private channel.

## Scope

### Must ship

- Booking attachment on an itinerary occurrence, with extraction to a review card
  and confirmation before any itinerary change.
- Traveler documents for passport and visa with structured fields.
- View, update, and delete for every stored record.
- Deterministic expiry and validity warnings surfaced on the trip.
- Deletion on privacy actions, and the security rules above.

### Should ship

- Insurance, vaccination, driving licence, and loyalty types.
- Optional masked identity appendix in the export.
- Grounded visa-free eligibility using the existing visa tool.

### Could ship later

- Forwarded-email ingestion and a trip inbox.
- Duplicate and conflict reconciliation across imported bookings.
- Offline packet generation for mobile.

### Out of scope

- Storing or rendering the original scan, photo, or PDF.
- `.docx` input in the first version.
- Payment instruments of any kind.
- Automated purchasing, cancellation, or provider order management.
- Sharing documents with anyone other than the owning account.
- Treating extracted text as legal or immigration advice.

## Staged delivery

1. **Field foundation:** the `documents` container, the capture and confirmation
   flow, list, view, edit, delete, and privacy deletion.
2. **Bookings:** PDF and image extraction into the review card and occurrence
   linkage.
3. **Traveler documents:** passport and visa fields, deterministic expiry checks.
4. **Insight and export:** grounded eligibility plus the optional masked appendix.

Each stage is independently useful and independently revertible.

## Open owner decisions

Retention and accepted file types are settled above. Three remain:

1. Confirm that guests cannot store identity documents.
2. Confirm the export default is off and masked when enabled.
3. Confirm the additional document types worth building, and whether emergency
   and medical notes should extend `family_members` rather than become documents.

The placement question - whether documents live in the trip, in the account, or in
an intake queue - is being answered by
[Lab #20](../ux-experiments/TRAVEL_DOCUMENTS.md) rather than decided here.