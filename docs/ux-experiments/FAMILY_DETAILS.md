# A family profile that grows with the trip

**Lab #26 · Open · 2026-08-14**

## Decision boundary

This Lab compares five low-pressure ways to capture family-wide context and individual traveler details. The family should not need to complete a biography before planning. The product can begin with a small useful fact, use it immediately, and learn more from real trip-building conversations over time.

The experiment does not change identity, privacy, document retention, persistence, agent behavior, or trip-specific overrides. It shows how the same typed facts could be presented and confirmed.

## Shared and individual information

**Shared family context** may include the home airport, common travel pace, default food pattern, typical room arrangement, emergency contact, and a preference for one central base.

**Individual context** may include age band, mobility, food restrictions, sleep rhythm, activity tolerance, room needs, and personal interests. A person-specific value is an exception to the shared default, not a duplicate profile users must fill twice.

Every fact carries a provenance state:

- **Explicitly saved**: the user chose Remember or entered it in the profile.
- **Suggested from chat**: the planner noticed a useful statement and asks before saving.
- **Trip-only context**: useful for the current trip, never added to the durable profile without confirmation.
- **Not now**: dismissed without being treated as a preference.

## Options

- **A · Family roster**: start with people cards and add a quiet set of relevant details for each person.
- **B · Trip questions**: ask only what the current trip needs, one small question at a time.
- **C · Shared defaults**: establish family norms first, then expose individual exceptions.
- **D · Chat-led profile**: surface tiny confirm-or-save suggestions inside real planning conversations.
- **E · Profile matrix**: compare the family across a few important dimensions before a trip.

## Design principles

1. Never show a wall of blank fields.
2. Make shared defaults and individual exceptions visibly different.
3. Every passive inference is reversible and requires explicit confirmation before becoming durable.
4. Keep trip-only context useful without silently promoting it into the profile.
5. Let a later review surface make accumulated learning legible.

## Review questions

- Which option feels easiest to start with when the profile is empty?
- Does the distinction between family defaults and individual needs feel natural?
- Does “Remember” make passive learning feel helpful rather than surveillant?
- Is the profile still easy to correct after a year of incremental additions?
