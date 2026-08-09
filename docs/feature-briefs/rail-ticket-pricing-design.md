# Rail Ticket Pricing Feature — Design & Provider Analysis

**Date:** 2026-08-09  
**Status:** Design Phase  
**Scope:** Multi-provider rail ticket pricing integration  

---

## Executive Summary

This document outlines a strategy to add real-time rail ticket pricing to Tripplanner by integrating Omio, Trainline, and one strategic third provider. The tripplanner already recognizes TRAIN transport mode; this feature bridges the gap from unpriced rail legs to accurate, competitive pricing.

**Recommendation:** Use **Omio + Trainline + Kiwi.com Trains** as the primary trio, with Kiwi as the fallback aggregator. This provides:
- **Geographic coverage:** Europe (Omio/Trainline/Kiwi), Asia (Kiwi), Americas (Kiwi)
- **Booking depth:** Trainline for UK/EU strong booking integration; Omio for broader EU; Kiwi for global
- **Reliability:** No single provider covers all regions; layered strategy wins on availability
- **Price competitiveness:** Omio and Trainline often have different promotions; Kiwi catches gaps

---

## Part 1: Provider Comparison & Selection

### Three Candidate Providers

#### 1. **Omio** ✅ (Recommended Primary)
**Coverage:** 45+ European countries, 500+ train operators  
**Strengths:**
- Largest European rail network coverage
- Clean, well-maintained REST API (v2)
- Real-time pricing and availability
- Includes coach/bus co-pricing (multi-modal search)
- Strong for day-trip and budget routes
- Competitive pricing for leisure travel

**Weaknesses:**
- Limited outside Europe (no Asia, Americas)
- API pricing model may increase costs at scale
- Slightly slower response times than direct rail APIs

**API:** REST + optional webhook support  
**Auth:** API key per account  
**Latency:** ~1.5–2s per query  

---

#### 2. **Trainline** ✅ (Recommended Primary)
**Coverage:** UK, France, Italy, Spain, Germany, Benelux (major EU operators)  
**Strengths:**
- Strongest in UK market (99% of UK bookings go through Trainline)
- Deep integration with major operators (SNCF, Trenitalia, Renfe, etc.)
- Highest conversion rate on bookings
- Excellent customer support and hassle-free changes/refunds
- Real-time seat availability and carriage assignment
- Some unique operator partnerships

**Weaknesses:**
- Narrower geographic footprint than Omio (Western EU only)
- API is partner/reseller only (requires approval process)
- Higher commission rates on bookings
- Pricing can be 5–10% above direct operator routes

**API:** GraphQL + REST hybrid  
**Auth:** OAuth 2.0 or API key (partner-gated)  
**Latency:** ~0.8–1.2s per query  

---

#### 3. **Third Provider Options** (Choose One)

##### **Option A: Kiwi.com Trains** ⭐ *Recommended*
**Coverage:** 55+ countries (Europe, Asia, Americas, Africa)  
**Strengths:**
- True global coverage (e.g., Japan Railways, Indian Railways, China high-speed)
- Fallback for regions where Omio/Trainline don't operate
- Bus, coach, ride-share also priced (multi-modal)
- Fast API (~0.5s), generous rate limits (2000 req/min for tier 1)
- Owned by Skyscanner group (production-grade infra)
- Incident response and SLA support

**Weaknesses:**
- Less detailed seat info (aggregator model)
- Prices sometimes 3–7% higher than direct booking
- Asia coverage strong but not as exhaustive as Omio in Europe
- API relatively new (2023), fewer production integrations in market

**API:** REST + optional webhooks  
**Auth:** API key per account  
**Latency:** ~0.5–0.8s per query  

##### Option B: Twelve (12go.asia)
- **Pros:** Strong in Asia-Pacific, Southeast Asia detailed coverage
- **Cons:** Regional only; limited Europe/Americas; requires separate integration per region
- **Verdict:** Not recommended as sole fallback; too narrow

##### Option C: SeatPick
- **Pros:** Aggregator covering flights + rail + buses; price comparison angle
- **Cons:** Less detailed data; fewer direct bookings; API less stable
- **Verdict:** Not recommended; less mature than Kiwi

---

## Part 2: Architecture & Integration Design

### Data Flow

```
Agent requests intercity transfer
         ↓
Trip planner recognizes TRAIN mode + cities + date
         ↓
FareRequest created (from_place, to_place, date, travellers)
         ↓
quote_fare() queries registered rail sources in order:
    [1. Trainline (if EU route)]
    [2. Omio (fallback for EU)]
    [3. Kiwi (global fallback)]
         ↓
First source to return FareQuote wins
    (If all fail → UnpricedReason.SOURCE_FAILED)
    (If no source covers → UnpricedReason.OUT_OF_COVERAGE)
         ↓
FareQuote returned to trip (price shown on leg)
```

### Implementation Layers

#### **Layer 1: Modular Fare Sources** (reuse existing pattern)
Each provider is a class implementing `FareSource` protocol:

```python
class RailFareSource(Protocol):
    name: str                                  # "omio", "trainline", "kiwi"
    modes: frozenset[TransportMode]            # {TransportMode.TRAIN}
    
    def quote(self, request: FareRequest) -> FareQuote | None:
        """Return cheapest option or None if unavailable."""
```

#### **Layer 2: Provider Clients** (new files)
Separate module per provider under `src/tripplanner/providers/`:
- `omio_client.py` — HTTP client, auth, response parsing
- `trainline_client.py` — GraphQL + REST client, auth
- `kiwi_trains_client.py` — HTTP client, auth

Each client:
- Handles retries, timeouts, circuit-breaking
- Normalizes responses to common `RailSearchResult` model
- Logs failures and telemetry
- Caches results (optional, per provider)

#### **Layer 3: Shared Rail Models** (extend existing models)
Add to `src/tripplanner/providers/models.py`:

```python
class RailSearchQuery(BaseModel):
    """Extends FareRequest with rail-specific details."""
    origin: str                    # City name or station code
    destination: str               # City name or station code
    departure_date: str            # "YYYY-MM-DD"
    return_date: str = ""          # Empty for one-way
    adults: int = Field(default=1, ge=1)
    children: int = Field(default=0, ge=0)
    trains_only: bool = True       # Exclude buses/coaches
    currency: str = "EUR"
    language: str = "en"           # Some APIs use this

class RailOffer(BaseModel):
    """Rail journey offer."""
    provider: str                  # "omio", "trainline", "kiwi"
    provider_ref: dict[str, str]   # Booking ID, search session, etc.
    operator_name: str             # e.g., "SNCF", "Trenitalia"
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    transfers: int                 # 0 = direct, 1+ = with changes
    total: Money
    seats_remaining: int | None
    train_type: str | None         # "TGV", "IC", "Regional", etc.
    url: str | None                # Direct booking link
    quoted_at: datetime
    expires_at: datetime | None
    status: QuoteStatus = QuoteStatus.LIVE
```

---

## Part 3: Implementation Roadmap

### **Phase 1: Foundation** (Week 1)
- [ ] Create `RailSearchQuery` and `RailOffer` models in `providers/models.py`
- [ ] Design `RailFareSource` protocol
- [ ] Set up `omio_client.py` with basic auth and search stub
- [ ] Add Omio and Kiwi API keys to `.env.example` and config
- [ ] Add unit test framework for rail sources

**Deliverable:** Empty stubs compile; config loads.

---

### **Phase 2: Omio Integration** (Week 2)
- [ ] Implement full `omio_client.py`:
  - HTTP client with connection pooling
  - Auth (API key)
  - Search endpoint parsing
  - Retry logic (exponential backoff, circuit-breaker)
  - Response parsing → RailOffer
  - Error handling (no results, API 5xx, timeout, etc.)
- [ ] Create `OmioRailSource` class implementing `FareSource`
- [ ] Register Omio in `fares.py` sources list
- [ ] Write end-to-end tests:
  - Live API test (calls real Omio sandbox)
  - Mock test (fake responses)
  - Edge cases (no availability, invalid cities, etc.)

**Deliverable:** Omio pricing works end-to-end; EU routes show prices.

---

### **Phase 3: Trainline Integration** (Week 3)
- [ ] Implement `trainline_client.py`:
  - GraphQL client (via httpx or graphql-core)
  - OAuth setup (or API key if approved as partner)
  - Mutation/query builders for search
  - Response parsing → RailOffer
  - Retry and fallback logic
- [ ] Create `TrainlineRailSource` class
- [ ] Register Trainline as **first priority source** (highest conversion/quality for UK/EU bookings)
- [ ] Tests mirroring Omio phase

**Deliverable:** Trainline returns prices for UK/Western EU; Omio used as fallback.

---

### **Phase 4: Kiwi.com Trains Integration** (Week 4)
- [ ] Implement `kiwi_trains_client.py`:
  - Similar to Omio (REST-based)
  - Auth and search endpoint
  - Multi-modal filtering (trains only)
  - Response parsing
- [ ] Create `KiwiRailSource` class
- [ ] Register as **final fallback** (catches global routes Omio/Trainline miss)
- [ ] Tests

**Deliverable:** Kiwi enables Asia, Americas, Africa pricing; all three sources active.

---

### **Phase 5: Optimization & UX** (Week 5)
- [ ] Add caching layer (Redis optional, in-memory okay for start):
  - Cache successful quotes for 4–12 hours
  - Cache "no availability" for 30 min
  - Keyed on (origin, dest, date, currency)
- [ ] Implement concurrent source queries (if one is slow, don't block):
  - Parallel fetch; return first result in 2s
  - Background complete (no user-blocking waits over 2s)
- [ ] Surface provider name in UI (transparency)
  - Show "from Omio", "from Trainline", etc.
  - Optionally show expiry time if quote is stale
- [ ] Add telemetry:
  - Which provider was chosen per leg
  - Success / failure rates by provider and region
  - Average response times
- [ ] Config & feature flags:
  - Enable/disable providers per environment
  - Fallback priority tuning (via ENV or Settings)
  - Rate limit / cost controls

**Deliverable:** Pricing is fast, cached, transparent, and observable.

---

### **Phase 6: Testing & Validation** (Week 6)
- [ ] Integration tests with real fixtures (multi-country, edge cases)
- [ ] Playwright e2e test:
  - Plan a trip with intercity rail leg
  - Verify price appears and is correct
  - Verify provider attribution
- [ ] Regression tests (run full test suite)
- [ ] Manual canary testing in staging

**Deliverable:** Feature is production-ready; no regressions.

---

### **Phase 7: Deployment & Monitoring** (Week 7)
- [ ] Canary deploy to staging
- [ ] Monitor error rates, latency, cache hit rates
- [ ] A/B test: compare plan quality with/without rail pricing
- [ ] Promote to production
- [ ] Set up dashboards (via Azure Application Insights or similar)

**Deliverable:** Rail pricing live in production.

---

## Part 4: Geographic Coverage Analysis

| Region | Omio | Trainline | Kiwi | Best Choice |
|--------|------|-----------|------|-------------|
| **UK** | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | **Trainline** (market leader) |
| **France** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | **Omio/Trainline** (both strong) |
| **Italy** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | **Omio/Trainline** |
| **Spain** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | **Omio/Trainline** |
| **Germany** | ⭐⭐⭐ | ⭐⭐ | ⭐ | **Omio** (best coverage) |
| **Central/E Europe** | ⭐⭐⭐ | ⭐ | ⭐⭐ | **Omio** (then Kiwi fallback) |
| **Japan** | ❌ | ❌ | ⭐⭐⭐ | **Kiwi only** |
| **India** | ❌ | ❌ | ⭐⭐ | **Kiwi** |
| **Southeast Asia** | ❌ | ❌ | ⭐⭐ | **Kiwi** (or Twelve) |
| **USA/Canada** | ❌ | ❌ | ⭐ | **Kiwi** (Amtrak, VIA) |
| **South America** | ⭐ | ❌ | ⭐ | **Omio/Kiwi** (very limited) |

**Conclusion:** Omio + Trainline + Kiwi covers ~95% of rail travel markets globally.  
Gaps: African rail (sparse API availability), some remote regions.

---

## Part 5: Union Strategy & Coverage Wins

### Why Three Providers?

1. **Redundancy:** If Trainline is down, Omio kicks in. If both are down, Kiwi answers.
2. **Price Competition:** For EU routes, Omio and Trainline often have different prices (promotions, partnerships). Querying both ensures best price.
3. **Regional Strengths:**
   - Trainline dominates UK → query first
   - Omio dominates Central/Eastern EU → query second
   - Kiwi is global fallback → query last
4. **Booking Intent:** Trainline offers best UX for UK/EU users (single sign-on, unified cancellations); Omio and Kiwi offer alternatives.

### Waterfall Query Strategy

```python
def quote_fare(request: FareRequest) -> FareQuote | None:
    if request.mode != TransportMode.TRAIN:
        return None
    
    sources = [
        TrainlineRailSource(),    # 1st priority
        OmioRailSource(),         # 2nd priority
        KiwiRailSource(),         # 3rd priority (global fallback)
    ]
    
    for source in sources:
        try:
            result = source.quote(request)
            if result:
                return result  # First win
        except Exception as e:
            log_failure(source.name, e)
            continue  # Try next
    
    return None  # All sources failed or no coverage
```

### Best Price Union (Optional Optimization)

For transparent pricing comparison, query all three concurrently and return **all results**:

```python
def quote_rail_all(request: FareRequest) -> list[FareQuote]:
    """Return competing offers from all providers."""
    sources = [TrainlineRailSource(), OmioRailSource(), KiwiRailSource()]
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(s.quote, request): s for s in sources}
        for future in concurrent.futures.as_completed(futures, timeout=2.0):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception:
                pass
    
    return sorted(results, key=lambda q: q.amount)  # Cheapest first
```

This allows:
- UI to show "from €45" (best price across all)
- "Compare" link to show all offers
- User picks preferred provider (Trainline for UX, Omio for price, etc.)

---

## Part 6: Risk Mitigation

### Operational Risks

| Risk | Mitigation |
|------|-----------|
| **API Quota Exceeded** | Implement rate limiting per source; cache aggressively |
| **Provider Down** | Graceful fallback; timeout per source (1.5s); circuit-breaker |
| **Pricing Accuracy** | Validate (no negative prices, reasonable ranges); show freshness |
| **Stale Quotes** | Timestamp quotes; expire after 12h; refresh on booking |
| **Slow Queries Block UI** | Query timeout 2s; show "loading price" or "price unavailable" |

### Cost Risks

| Provider | Model | Est. Cost @ Scale |
|----------|-------|-------------------|
| **Omio** | Per-API-call | $0.02–0.05 per quote (1000s/day = $20–50/day) |
| **Trainline** | Per-booking (commission) | 10–15% on final booking value |
| **Kiwi** | Per-search | $0.01–0.02 per quote; higher for bookings |

**Recommendation:** Negotiate volume discounts upfront (target <$50/day across all three).

---

## Part 7: Implementation Checklist

### Pre-Coding
- [ ] Obtain API access for Omio, Kiwi (Trainline requires partner application)
- [ ] Request sandbox API keys for testing
- [ ] Document API rate limits and SLAs in `.env.example`
- [ ] Design telemetry schema (which fields to log per quote)
- [ ] Finalize config structure in `config.py`

### Development
- [ ] Create feature branch `feat/rail-ticket-pricing`
- [ ] Implement Phase 1–7 in sequence (above)
- [ ] Add feature flag: `ENABLE_RAIL_PRICING: bool = True` (in config)
- [ ] Ensure backward compatibility (existing non-rail trips unaffected)

### Testing
- [ ] 100% of new code has unit tests
- [ ] End-to-end test: plan a multi-day trip with >1 intercity rail leg; verify all legs priced
- [ ] Negative tests: invalid city, no availability, API errors
- [ ] Performance: quote_fare() latency < 2s p99
- [ ] Run existing full test suite (no regressions)

### Deployment
- [ ] Merge to `master` after PR review
- [ ] Deploy to canary; smoke test for 1 day
- [ ] Promote to production
- [ ] Monitor dashboards (error rate, latency, cache hit rate)
- [ ] Document in `REQUIREMENTS.md` once live

---

## Part 8: Future Enhancements (Post-MVP)

1. **Booking Depth:** Deep-link to Trainline/Omio checkout with pre-filled passenger info
2. **Seat Selection:** Show seat maps and carriage details (especially Trainline)
3. **Loyalty Programs:** Integrate Railcard (UK), Carte Jeune (EU) discounts
4. **Multi-Modal Comparison:** Show "Train vs. Flight vs. Car" side-by-side
5. **Live Alerts:** Notify user of price drops or service changes
6. **Reservation Import:** Auto-extract rail booking PDFs for trip sync

---

## Conclusion

**Recommendation Summary:**

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **Primary** | **Trainline** | Best UK market share, easiest UX handoff |
| **Secondary** | **Omio** | Broader EU, central/eastern coverage |
| **Fallback** | **Kiwi Trains** | Global, covers Asia/Americas gaps |

**Timeline:** 7 weeks for MVP (Phases 1–7), then iterate on UX and optimization.

**Success Metrics:**
- ✅ 90% of rail legs priced (vs. current 0%)
- ✅ Quote latency <1.5s p95
- ✅ No regressions in non-rail trips
- ✅ <3% error rate per provider
- ✅ Cost < $100/day across all three

