# Product Analytics

GA4 is the product-analytics system for `aitripplanner.co`. Azure Log Analytics
remains the operational source for request outcomes, latency, tools, and errors.
Do not send chat text, itinerary content, destinations, dates, account identity,
email addresses, or shared-link tokens to GA4.

## Production setup

The `AI Trip Planner Production` GA4 property has an `aitripplanner production`
Web stream for `https://aitripplanner.co` with measurement ID `G-VNTSQG9SWZ`.
Optional account data sharing and Enhanced Measurement are disabled.

The public measurement ID is committed only in `infra/prod.bicepparam`. Deploy
through the normal canary and production promotion flow. Analytics is runtime-gated
to `TRIPPLANNER_ENVIRONMENT=prod`; local and canary return a disabled configuration.

After an approved production deployment:

1. Choose **Allow analytics** on production.
2. Use GA4 Realtime to confirm `page_view` and one normal planning flow.
3. Reopen the choice from Account -> Analytics preferences and verify revocation.

No GA script is loaded before consent. The manual page view strips the query
string so shared-trip tokens are not collected. Consent is stored only in the
browser and can be changed later.

Consented events also fan out to the hidden first-party aggregate endpoint used
by the owner operations dashboard. That endpoint accepts only the event name, a
random browser-session ID, and a bounded source category. It ignores event
parameters and does not retain URLs, referrers, account IDs, emails, prompts,
destinations, dates, trip IDs, or cache keys. Its funnel, engagement, source, and
drop-off metrics are process-local and reset with the container; GA4 remains the
durable authority for acquisition, country, retention, and historical funnels.

## Event vocabulary

| Event | Meaning | Parameters |
|---|---|---|
| `page_view` | Consented production app visit | Query-free location, page title |
| `planning_started` | A prompt was submitted | `proposal_only`, `retry` |
| `planning_completed` | The streamed planning turn completed | `proposal_only` |
| `planning_failed` | The planning turn failed | `proposal_only` |
| `trip_created` | A completed turn established a new trip ID | None |
| `new_trip_started` | Existing workspace was reset | `surface` |
| `login` | Sign-in action or completion | Fixed `method` enum |
| `place_added` | A place mutation succeeded | `exact_day` |
| `place_removed` | A place mutation succeeded | Fixed `scope` enum |
| `trip_shared` | A read-only share link was created | None |
| `shared_trip_imported` | A shared trip import succeeded | None |
| `itinerary_exported` | Preview, print, PDF, or email succeeded/started | Fixed `method` enum |
| `calendar_exported` | Calendar download was selected | None |

Keep this vocabulary small. New parameters must be bounded enums, numbers, or
booleans and must pass the same no-content rule.

## Reports to create

Create a GA4 funnel exploration with:

1. `page_view`
2. `planning_started`
3. `trip_created`
4. `planning_completed`
5. Any of `itinerary_exported`, `trip_shared`, or `calendar_exported`

Use breakdowns for device category, new/returning user, source/medium, and
country. Also monitor planning failure rate and median time between
`planning_started` and `planning_completed`. Mark `trip_created`,
`itinerary_exported`, `trip_shared`, and `calendar_exported` as key events.

GA4 answers acquisition and customer-flow questions. Diagnose a conversion drop
against the PII-safe `chat_operation` and `tool_call` queries in
`operations-slos.md`; do not copy operational exception details into GA4.

The hidden `/operations` route provides two live views:

- **Business**: consented activities, users, active engagement time, source
	categories, observed funnel stage, and persisted trip counts.
- **System Health**: chat/model/API latency, tool and fare-provider failures,
	top cache-hit tool categories, Redis namespace size, and selected trip items.

Dashboard labels distinguish process-local, monthly persisted, and rolling
30-day values. An observed drop-off describes the last measured stage; it must
not be presented as a subjective reason for leaving.