# Travel documents: where they live, and what we refuse to keep

## Meta

- Branch: not retained; current implementation work uses a sandbox
- Owner: Munish Goyal
- Date started: 6-Aug-2026
- Date ended: 7-Aug-2026
- Status: Selected — B · Account vault, trip shows gaps
- Lab: `http://127.0.0.1:5175/lab-20-travel-documents.html`
- Full-size preview: append `?preview=readiness`, `?preview=vault`, or `?preview=inbox`
- Feature brief: [`../feature-briefs/002-travel-documents.md`](../feature-briefs/002-travel-documents.md)

## The gap this Lab answers

Everything the owner books arrives as a file, and none of those files have a home. A flight
confirmation lives in email, a hotel reference lives in a screenshot, and the passport that
decides whether the trip is legal at all lives nowhere the planner can see. Three concrete
failures follow:

1. **The export is incomplete.** The trip PDF describes days and stops but cannot print the
   confirmation number the owner will actually be asked for at the desk.
2. **The planner cannot warn.** A passport that expires seven weeks after the return date
   fails Portugal's three-month validity rule, and nothing in the product knows.
3. **Every trip starts from zero.** The same passport, for the same three travellers, has to
   be produced again on the next trip, because nothing was remembered.

## Decided before the Lab opened

The owner settled the retention question directly: **the original document is never stored.**
A photo or PDF is read once, the fields that answer a planning question are kept, and the
file is discarded. The stored fields are what gets reused on the next trip, which is what
stops the product asking for the same passport twice.

| What we read | What it answers | Retention |
| --- | --- | --- |
| Issuing country | Whether a visa is required at all | Kept |
| Expiry date | Destination validity rule, renewal warning | Kept |
| Date of birth | Child fares, age limits, minor-consent rules | Kept |
| Visa type, window, entries | Whether this trip fits an existing visa | Kept |
| Insurance cover, assistance line | Destination medical minimum, a number to call | Kept |
| Document number | No check needs it; only form-filling does | Last four only |
| The photo, scan or PDF | Nothing, once the fields are read | **Never stored** |

Two consequences are worth stating plainly. A breach of this application leaks four
digits and an expiry date rather than a scan of someone's identity. And there is no
blob store to secure, expire, rotate or reason about in the privacy-deletion path.

`.docx` is out of v1. PDF, JPEG, PNG, HEIC and pasted text cover every case the owner
actually encounters.

Two further decisions landed on 6-Aug-2026. Identity documents require a signed-in
account, which makes the security boundary and the sign-up incentive the same line.
And all five additional types ship in v1 — insurance, vaccination, driving licence,
International Driving Permit, loyalty — because each answers a check the planner can
actually run. Emergency contacts and medical notes stay profile fields; they have no
document to extract from.

## Two lifetimes hiding inside one word

"Document" covers two things that behave nothing alike:

- **Yours, and permanent.** Passport, visa, insurance, vaccination. Captured once, reused by
  every future trip. These outlive any single itinerary.
- **The trip's, and disposable.** Flight confirmations, hotel references, timed-entry codes.
  They attach to one stop on one day and stop mattering when the trip ends.

The three options disagree about exactly one thing: whether those two lifetimes deserve two
homes, one home, or one door.

## Options

### A · Trip readiness rail

The trip's third pane becomes Readiness: blockers first, then each traveller with what is on
file, then the checks that already pass. Documents are added from the row that is missing
one, and reviewed in place.

**Exact delta.** The trip owns the entire subject, so there is exactly one place to look and
nothing to manage elsewhere — unlike B, which splits by lifetime, and unlike C, which
separates intake from placement. The cost is the Details pane, which is where the owner
decides about the place they are currently looking at.

### B · Account vault, trip shows gaps

Traveller details live permanently in Account. The trip carries one honest badge — *2
documents to fix* — that opens the vault focused on this trip's gaps. Details keeps its pane.
Booking references attach directly to the itinerary stop they belong to.

**Exact delta.** Two homes matched to the two lifetimes, so the trip never becomes a document
manager — unlike A, which puts a permanent account concern inside one itinerary. The answer
is one click away rather than already on screen, which is the trade against A.

### C · Document inbox

One dock takes anything dropped into it. Items land as *Needs review*, are read in the
background, and route themselves: bookings to their stop, identity to the traveller.

**Exact delta.** Intake is decoupled from placement, so six email attachments can be dumped
in one gesture and triaged later — unlike A and B, which both require the owner to say what
a file is before it is accepted. The cost is a second queue that can go stale, and a trip
that can look ready while unreviewed items sit in the dock.

## Required in every option

1. The original file is read once and discarded. Only extracted fields persist, and an
   identity number persists as its last four digits.
2. Extraction never writes to the trip on its own. Every field is confirmed first, with the
   confidence that produced it.
3. Details captured once are reused on the next trip without asking, and the reuse is visible
   ("Reused from Kyoto, Mar 2026").
4. Deterministic checks — validity windows, cover amounts, date arithmetic — are computed in
   code, never inferred by the model.
5. Eligibility claims are grounded in a live source and carry the source and check date.
6. A booking document attaches to the exact day and stop it belongs to, and marks it booked.
7. Every stored detail can be viewed, corrected and deleted from one place.
8. Nothing from this feature ever enters a share link, whatever the export settings say.

## Fixture

A Lisbon trip, 8–13 Oct 2026, for three Indian-passport travellers. The facts are chosen so
the checks have real answers rather than decorative badges:

| Check | Result | Origin |
| --- | --- | --- |
| Priya's passport expires 20 Nov 2026 | **Blocker** — 38 days after exit, against a 3-month rule | Computed |
| Aarav has no passport on file | **Blocker** — he is on the flight and the hotel booking | Computed |
| Aarav has no Schengen visa | **Blocker** — Indian passport requires a Type C visa | Grounded |
| Indian licence, no International Driving Permit | **Warning** — day 3 is a Sintra drive; the rental desk refuses the car | Grounded |
| Munish's visa 1 Jun – 15 Dec 2026 | Clear — 63 days of margin | Computed |
| Insurance €50,000 medical | Clear — against a €30,000 Schengen minimum | Grounded |

The licence row exists to answer a fair question: why store a driving licence at
all? Because the licence alone is not the check. A non-EU licence is accepted in
Portugal only alongside an International Driving Permit, and that is a same-day
errand at home and an impossible one at the rental desk.

## Guardrails

- No original document is written to storage, so there is nothing to leak, expire or rotate.
- Only the last four digits of an identity number are stored, so no export, reveal or breach
  can produce the rest. Provider references — booking, policy, loyalty — stay whole, because
  being quoted is their purpose.
- `sanitize_plan` in `src/tripplanner/web/share.py` stays an allowlist. No document field is
  ever added to it, so share links cannot regress into leaking identity data.
- `/account/privacy` must delete these records too. A privacy wipe that reports success while
  details survive is worse than no wipe at all.
- Guests cannot store identity details. A capability credential is not an identity.
- Insurance, vaccination and licence details follow the same rule as passports: fields in,
  file out.

## Out of scope

- Storing or rendering the original scan, photo or PDF.
- `.docx` in v1.
- Payment instruments of any kind. Card numbers have no planning value and unbounded downside.
- Filling or submitting a visa application on the owner's behalf.

## Supersedes

The non-goal recorded in [`ITINERARY_TRIP_BOOK.md`](ITINERARY_TRIP_BOOK.md) and
[`README.md`](README.md) — that travel-document upload stays out of scope "until a direction
is selected and separately approved" — is answered by this Lab. The owner approved the
capability on 6-Aug-2026; the direction is what this Lab now selects.

## How to judge

| Criterion | Question |
| --- | --- |
| Second-trip cost | On the next trip, how much is asked for again? The correct answer is nothing. |
| Blocker legibility | Is it clear *why* Priya's passport fails, without reading a rule number? |
| Time to first value | How long until "two people cannot travel" is visible? |
| Clutter cost | What does the surface cost when everything is already in order? |
| Trust in extraction | Is it obvious what was read, how sure it was, and that the file is gone? |
| Recovery | A wrong expiry was saved. How many steps to find and fix it? |

## Decision

**B · Account vault, trip shows gaps.** Details live in Account, permanently and once. A
trip never owns a document; it carries a single badge naming how many documents need
fixing, and that badge opens the vault already scrolled to this trip's gaps. B is the only
option where the second trip costs nothing, which was the criterion that mattered most.

### What shipped

Three backend modules, deliberately separated by lifetime rather than by layer:
`travel_documents.py` decides what may be stored, `document_readiness.py` decides what to
say about it, and `document_extract.py` reads a photo or pasted text once and returns
proposals it does not persist. Endpoints are `GET /documents`, `POST /documents`,
`POST /documents/extract`, `POST /documents/delete`, `POST /documents/clear`, and
`GET /trip/documents/readiness`.

The guardrails are enforced in code, not documented as intentions. Any field outside the
per-type allowlist is dropped on save; `number`, `document_number` and `identity_number`
are all folded into `number_last4` before anything is written, so a caller cannot store a
full identity number even by asking. `/account/privacy` deletes these records and reports
the count. `sanitize_plan` was not touched.

Two scope decisions worth stating. PDFs are refused with an explicit message rather than
silently failing, because no PDF reader is a dependency and pretending otherwise would be
worse than the refusal; photographing the page or pasting the text both work. And the
passport margin check names the six-month margin it used and asks the owner to confirm
the destination's exact rule, rather than claiming a per-country rule the product does not
actually hold.

### What the first build got wrong, and the rule that replaced it

The passport check fired on every trip that had dates. A weekend in Goa, planned from
Bengaluru, showed a red "1 document to fix" for a passport the trip did not need. It was
also the only check that alarmed on an *absence*: visa, insurance and permit checks all
required a record to exist before they said anything.

Two rules now govern every check:

- **Silent unless the trip is known to cross a border.** The deciding fact is the trip's
  own `origin` — already persisted, already learned opportunistically when the owner says
  "I'll fly in from Bangalore", already falling back to the profile's home area. Origin and
  destination are each resolved to a country through `place_country.py`, and the passport,
  visa and IDP checks run only when the two differ. Unknown on either side is treated as
  no border, so a geocoder outage produces silence rather than a false alarm. Citizenship
  is deliberately not collected: it is a visa question, and `tools/visa.py` already answers
  grounded visa questions properly.
- **Absence warns, arithmetic blocks.** A missing passport record is now a warning worded
  as what it actually is — "this trip leaves India, and nothing on this account records a
  passport for this traveller, so no expiry check can run" — because crossing a border is
  not the same as needing a passport (Schengen, India–Nepal, the UK–Ireland CTA). Only a
  stored date that fails a comparison can raise a blocker. The toolbar badge is rose for
  blockers and amber for warnings, so red keeps meaning "we proved something is wrong".

The same rigour was applied to the other types rather than to passports alone. A dual
national's lapsed second passport no longer raises a blocker: the latest expiry is the one
measured. A visa naming another country is ignored entirely; a visa naming no country is
still read, but only as a warning that says it may not be the visa that matters here. A
licence issued by the destination country needs no International Driving Permit, and the
IDP prompt no longer appears on domestic trips. Insurance and stored expiry dates stay
active everywhere, because they are arithmetic over records the owner chose to keep, and
they matter at home too. A lapsed loyalty tier is not worth a badge.
