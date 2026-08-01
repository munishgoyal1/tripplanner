# Experiment: Multi-city transition-day itinerary

## Meta

- Owner: Munish Goyal
- Date started: 2026-08-01
- Status: testing
- Lab: `http://127.0.0.1:5175/multi-city-itinerary.html`

## Problem

Multi-city days contain two different stay contexts. The itinerary must make
checkout from the origin stay, the complete inter-city journey, check-in at the
destination stay, and any remaining destination plans understandable as one
chronological day. A generic list can obscure the stay handoff or make transfer
time look like another local stop.

Road and rail journeys are continuous ground movements through named endpoints.
Flights need separate hotel-to-airport and airport-to-hotel context around the
airport-to-airport leg. All three modes must retain auditable departure, arrival,
duration, and endpoint information.

## Scope

- Compare the hierarchy of checkout, travel, arrival, check-in, and the remaining day.
- Compare a chronological spine, a stay-to-stay handoff, and city chapters.
- Switch among realistic road, rail, and flight states in every option.
- Preserve stop order, timing, hotel identity, booking state, Map behavior,
  route providers, and planning logic as context only.

## Variants

- **A - Transition spine:** one chronological chain keeps both stay endpoints
  and the complete journey auditable without splitting the day into cards. It
  uses neither B's paired hotel cards nor C's city chapters.
- **B - Stay handoff:** the origin and destination hotels frame a prominent
  transfer object, with the destination evening retained below. It replaces A's
  single timeline and does not introduce C's Morning/Journey/Evening sections.
- **C - City chapters:** Morning in the origin city, Journey, and Evening in the
  destination city make the change in place context explicit. It uses neither
  A's continuous spine nor B's paired hotel handoff.

## Current recommendation

Start with **A - Transition spine**. It is closest to the authoritative schedule,
keeps every endpoint in one scan path, and supports road, rail, and flight without
turning one calendar day into separate itinerary days. This recommendation is
not implementation approval.

## Decision

- Decision: pending owner evaluation
- Production implementation status: not implemented
- Next action: compare all three interactions and save one implementation handoff