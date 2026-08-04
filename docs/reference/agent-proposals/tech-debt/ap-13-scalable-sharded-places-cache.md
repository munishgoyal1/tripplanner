# ap-13 — Scalable sharded places_cache (remove the 2 MiB durable ceiling)

- **Status:** Approved by owner 2026-08-04; implementing.
- **Supersedes:** the durable-layer sub-parts of tech-debt #1 (byte-size guard). The
  in-memory L1 cache and the code-level TTL are unchanged.

## Problem

The durable (L2) cache persists **every place as a single Cosmos document**
(`container=places_cache`, partition `_shared`, `id="cache"`, body `{"entries": {…}}`).
Cosmos enforces a hard **2 MiB per-item limit**, so that one document cannot grow past
it — production logs showed `RequestEntityTooLarge` at ~2.4 MiB. The item-count eviction
(`_MAX_ENTRIES`) never looked at bytes.

The interim guard (ap tech-debt #1) keeps the doc under ~1.9 MB by dropping the oldest
entries. That stops the error but leaves a **hard ceiling**: only ~a few hundred places
survive a restart; at production scale (many users → many distinct places) the rest
re-fetch from Google on every cold start (ACA scales to zero), costing latency and API
spend. Correctness is fine (L1 always serves), but the durable cache stops paying off.

## Design — one document per place key

- **Durable schema:** one Cosmos item per cache key instead of a monolithic doc.
  `id = sha1(key)` (keys contain spaces/`/`/`|`, which are illegal in a Cosmos id), body
  `{"key": <original key>, "entry": <entry minus volatile photo fields>}`. Each item is
  ~1–5 KB — far under 2 MiB. The container scales to ~20 GB per logical partition
  (millions of places).
- **Lazy per-key load:** drop the bulk startup read when Cosmos is enabled. On an L1
  miss, point-read the single key (`read_doc`, ~1 RU) before falling back to Google.
  Memory stays bounded by the existing L1 cap; the durable store scales independently.
- **Per-key upsert:** each getter persists only the key it touched, which also removes
  today's write-amplification (one `/trip/view` no longer rewrites the whole doc 10×).
  Batched warming (`_batched_persist`) flushes the set of dirty keys.
- **Local dev store unchanged:** when Cosmos is disabled we keep the single-file JSON
  snapshot (no size limit, tiny scale) — no behavior change for local development.
- **Legacy cleanup:** best-effort one-time delete of the old `id="cache"` document after
  the first successful sharded write.

## Deliberately deferred (not in this change)

- **Native Cosmos TTL** per item (auto-expiry) requires enabling container TTL (infra).
  Kept code-level `_fresh`/`_META_TTL_S` for now; stale per-key docs are ignored on read
  and overwritten. Each is tiny, so accumulation is negligible. Follow-up if desired.
- **Hash-bucketed partition key** for throughput distribution at very high scale — the
  single `_shared` logical partition (20 GB) is ample for this app.

## Risk

- **Medium (storage-schema change), API-behavior-preserving.** No response shape or
  served-data change. The old monolithic doc is orphaned then cleaned up; new reads use
  hashed per-key ids, so there is no collision or migration window.

## Acceptance

- No `RequestEntityTooLarge` regardless of total place count.
- L1 hit path unchanged; on L1 miss with Cosmos enabled, a warm key is served from a
  per-key Cosmos read without calling Google.
- Cosmos persists one document per touched key; batched warming flushes all dirty keys.
- Local-dev (Cosmos disabled) persistence and load are unchanged.
- `pytest tests/test_places_cache.py` green, including new sharding tests.
