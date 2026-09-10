# Azure OpenAI planning-model performance — 2026-09

Verified 2026-09-10 against checked-in environment profiles, the versioned
planning catalog, public Azure OpenAI Global Standard token tables (snapshot
2026-09-09), and the current Places/tool budgets. This is dated research, not
an approval to change the hosted deployment. Azure Cost Management and Google
Cloud Billing remain authoritative for billed spend.

## What is actually running

Local, canary, and production profiles all set:

```dotenv
AZURE_OPENAI_DEPLOYMENT=gpt-5.4-mini
AZURE_OPENAI_MODEL_VERSION=2026-03-17
```

Canonical docs still named GPT-4.1 as the default. That was stale. The live
planner is already on the GPT-5.4 mini SKU in the existing Azure OpenAI
resource `aoaiprodtp9fe3951c`.

The monthly usage-cap estimator previously matched every `gpt-5*` name to a
generic GPT-5 row, so `gpt-5.4-mini` was overstated at about 4× its list price.
The catalog now uses longest-prefix matching.

## What “performance” means here

Score a candidate on one combined heading, not on quality or price alone:

| Weight | Dimension | Tripplanner meaning |
| --- | ---: | --- |
| 35 | Itinerary quality | Local-expert standard in [PRODUCT.md](../PRODUCT.md): ritual/admission windows, realistic days, preference fit, named restaurants, no filler. Fewer later Assistant corrections. |
| 25 | Paid-tool leverage | Fewer cold Google Places/Routes calls and fewer fishing tool rounds for the same grounded plan. Model knowledge proposes; Places/hours/inventory still verify. |
| 20 | Wall-clock | Stay inside the 2–4 minute full-build expectation. Extra reasoning tokens that add a minute without changing the plan fail this. |
| 15 | Token cost | Azure list-price USD (and INR at the planning FX of 88) per completed new-trip turn, including retries. |
| 5 | Operational fit | Available on this Azure resource, stable enough for streaming + tools, not a coding/Codex SKU. |

A model wins only if the weighted score beats the current default on a
measured corpus, not because it is newer or larger.

## Nearby Azure OpenAI models

List prices below are USD per 1 million tokens, Global Standard, catalog
`2026-09-10`. They are planning assumptions.

| Model | Input | Output | Role vs this product |
| --- | ---: | ---: | --- |
| **gpt-5.4-mini (current)** | $0.75 | $4.50 | Default. Strong enough for tool-using itineraries; cheaper than GPT-5 and GPT-5.4. |
| gpt-5-mini | $0.25 | $2.00 | Cheaper sibling. Risk: more generic plans and extra Places/search rounds. |
| gpt-5.4-nano / gpt-5-nano | $0.20 / $0.05 | $1.25 / $0.40 | Too weak for local-expert synthesis. |
| gpt-5 / gpt-5.1 | $1.25 | $10.00 | Older flagship than 5.4. Skip as an upgrade from mini; if spending more, spend it on 5.4. |
| gpt-5.2 | $1.75 | $14.00 | Mid-flagship. Unlikely to beat 5.4 on travel nuance at a lower price. |
| **gpt-5.4** | $2.50 | $15.00 | Next upgrade candidate when mini quality or tool-round counts fail. |
| gpt-4.1 | $2.00 | $8.00 | Previous documented default. Similar token cost to GPT-5, weaker current reasoning. Do not go back. |
| gpt-5.5 / GPT-5.4 Pro | $5–$30 | $30–$180 | Fails the monthly Azure budget (6,000 INR planning ceiling) for routine trips. |
| o3 / o4-mini | $2.00 / $1.10 | $8.00 / $4.40 | Extra reasoning latency without better live place facts. |
| Codex / gpt-5.6-sol | n/a here | n/a | Coding workers only. Not a travel planner. |

World knowledge, however recent, does not replace Google Places hours, ratings,
photos, or hotel/flight inventory. The win from a smarter model is **fewer,
better-targeted** paid calls and **fewer traveller round-trips**, not skipping
verification.

## Approximate cost per new-trip itinerary

Assumptions (catalog, not invoices):

- One new-trip Assistant turn, 8 model rounds (tool-phase budget is 10).
- Typical: 160k prompt + 12k completion tokens across the turn.
- Heavy (long destination, many tools, little cache): 400k prompt + 30k completion.
- Cold Google Places ceiling already configured: 3 text searches, 1 review
  details, 3 photos ≈ **$0.14 / INR 12** at the existing Maps catalog, before
  free-tier pooling. Cache hits can make Google ≈ $0.
- FX: INR 88 / USD (same planning rate as the GCP cost model).

| Model | Typical Azure | Heavy Azure | Typical + cold Places | Heavy + cold Places |
| --- | ---: | ---: | ---: | ---: |
| gpt-5-mini | $0.06 / ₹5 | $0.16 / ₹14 | $0.20 / ₹18 | $0.30 / ₹26 |
| **gpt-5.4-mini** | **$0.17 / ₹15** | **$0.44 / ₹38** | **$0.32 / ₹28** | **$0.58 / ₹51** |
| gpt-5 | $0.32 / ₹28 | $0.80 / ₹70 | $0.46 / ₹40 | $0.94 / ₹83 |
| gpt-4.1 | $0.42 / ₹37 | $1.04 / ₹92 | $0.56 / ₹49 | $1.18 / ₹104 |
| **gpt-5.4** | **$0.58 / ₹51** | **$1.45 / ₹128** | **$0.72 / ₹63** | **$1.59 / ₹140** |
| gpt-5.5 | $1.16 / ₹102 | $2.90 / ₹255 | $1.30 / ₹114 | $3.04 / ₹268 |

Prompt caching (about 90% off cached input on the GPT-5.4 family) can cut the
Azure line on later rounds; the table ignores that discount so the cap stays
conservative.

Against the **6,000 INR / month** Azure notification budget, typical
`gpt-5.4-mini` Azure-only trips leave room for hundreds of plans; typical
`gpt-5.4` full trips are about 3× that Azure line. Production’s 1,800 INR share
is the tighter hosted constraint.

A model that saves even one extra Assistant correction turn, or two cold Places
Pro searches, often pays for itself only if the token delta is small. Mini →
full GPT-5.4 costs ~₹36 more Azure on a typical turn; that is worth it only
when it removes a failed plan or a second 2–4 minute build.

## Rubric to change the default

Keep `gpt-5.4-mini` unless a measured comparison against the trip-quality
corpus and a handful of owner trips shows **all** of:

1. Materially better local-expert itineraries (named, timed, constraint-true)
   on the same prompts, not just longer prose.
2. Fewer tool phases or fewer cold Places calls for the same groundedness, or
   fewer follow-up Assistant turns to reach a useful draft.
3. p95 full-build still inside the 2–4 minute product expectation.
4. Extra Azure USD per trip is smaller than the Places + retry savings, or is
   explicitly accepted against the monthly budget.

Then the upgrade target is **gpt-5.4** on the same Azure resource, not GPT-5,
GPT-5.2, or a Pro SKU. A cheaper experiment, if quality is already excellent,
is **gpt-5-mini**, scored the same way; do not switch to nano.

Changing `AZURE_OPENAI_DEPLOYMENT` in environment profiles is a runtime
behavior change and still needs explicit owner consent plus a local restart or
hosted deployment.

## Product vision

[PRODUCT.md](../PRODUCT.md) already states the intent at the right altitude:
best itinerary first, then best practical price, without losing a fast, breezy
planner; local-expert judgement; automation-first with almost no back-and-forth;
cache and bounded Places spend. This audit does not add a new north star. It
only replaces the stale “GPT-4.1 remains the planning model” line with a
performance rule that matches that vision.
