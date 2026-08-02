# Reference Source Material

This directory keeps owner-driven source material discoverable without mixing it
with maintained product and architecture truth. It includes original owner
inputs, chronological decision context, and inactive artifacts retained from
owner-directed work.

Current behavior is governed by the canonical documents at the `docs/` root:
`PRODUCT.md`, `REQUIREMENTS.md`, `CODEMAP.md`, and `ENGINEERING_LEARNINGS.md`.
Reference material can explain intent and history, but it does not override those
files.

## Owner inputs

| File | Purpose | Retention status |
| --- | --- | --- |
| [`owner-inputs/Requirements.docx`](owner-inputs/Requirements.docx) | Active owner-authored requirements input | Keep until the owner confirms it is superseded |
| [`owner-inputs/Overall.txt`](owner-inputs/Overall.txt) | Truncated note containing only `-Extra row at top of` | Removal candidate; owner approval required |
| [`owner-inputs/TripPlanner.txt`](owner-inputs/TripPlanner.txt) | Early top-level planner goal | Duplicate candidate; owner approval required before removal |
| [`owner-inputs/ChatAssistant.txt`](owner-inputs/ChatAssistant.txt) | Early Assistant journey and UX ideas | Historical design input; owner approval required before consolidation |
| [`owner-inputs/Itinerary.txt`](owner-inputs/Itinerary.txt) | Early itinerary, export, and personalization ideas | Historical design input; owner approval required before consolidation |
| [`owner-inputs/Performance.txt`](owner-inputs/Performance.txt) | Original latency concern | Historical problem statement; owner approval required before removal |

## History

| File | Purpose | Retention status |
| --- | --- | --- |
| [`history/requirements-log.txt`](history/requirements-log.txt) | Append-only chronological requirements and decision history | Retain; older entries may be obsolete but preserve rationale |
| [`history/framework-snapshot-2026-06-05.txt`](history/framework-snapshot-2026-06-05.txt) | Dated framework inventory and candidates | Stale snapshot; owner approval required before removal |

## Archive

These inactive artifacts remain available for provenance. They do not describe
current behavior.

| File | Purpose | Retention status |
| --- | --- | --- |
| [`archive/Bugs to resolve.docx`](archive/Bugs%20to%20resolve.docx) | Historical owner bug list | Retain until the owner approves consolidation or removal |
| [`archive/AI Trip Planner - Memory Architecture Specification v1.pdf`](archive/AI%20Trip%20Planner%20-%20Memory%20Architecture%20Specification%20v1.pdf) | Historical memory architecture proposal | Retain until the owner approves consolidation or removal |
| [`archive/key_info_infra.txt`](archive/key_info_infra.txt) | Historical infrastructure notes | Retain until the owner approves consolidation or removal |
| [`archive/myprompts.txt`](archive/myprompts.txt) | Historical prompt collection | Retain until the owner approves consolidation or removal |
| [`archive/usage.txt`](archive/usage.txt) | Historical usage notes | Retain until the owner approves consolidation or removal |

## Maintenance

- Add current product, capability, architecture, or engineering truth to its
  canonical owner instead of adding another reference file.
- Append new dated decisions to `history/requirements-log.txt`.
- Preserve owner-input files verbatim unless the owner approves consolidation or
  removal.
- Keep this index current when a reference is added, moved, archived, or removed.
