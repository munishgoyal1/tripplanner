# Profile, in choices you can see

**Lab #25 · Open · 2026-08-14**

## Decision boundary

This Lab reimagines the Profile settings panel that owns About me, durable travel preferences, and supporting traveler context. It compares how users choose known preferences quickly while keeping the planner's internal vocabulary precise.

The options do not change production persistence, authentication, privacy, the agent prompt contract, or one-trip overrides. The preview uses a fixed profile and the same preference schema in every option.

## Internal preference contract

Friendly labels are presentation. The stored values remain stable and machine-readable:

| Category | Internal key | Example values |
| --- | --- | --- |
| Trip rhythm | `trip_pace` | `balanced`, `see_it_all`, `relaxed` |
| Planning style | `planning_style` | `surprise_me`, `show_options`, `flexible` |
| Where you stay | `stay_style` | `central_walkable`, `quiet_retreat`, `best_value` |
| Food and flavour | `food` | `local_favourites`, `vegetarian`, `food_centric` |

Typing remains an escape hatch for future long-tail preferences, but the primary path is choosing from visible tags.

## Options

- **A · Preference shelf**: a complete profile home with category sections, quick-select buttons, optional About me notes, and an always-visible “What Tripplanner understands” mapping panel.
- **B · Trip briefing**: one preference group at a time with a friendly question, progress count, and Next preference action.
- **C · Command palette**: a searchable preference surface for precise power-user edits while retaining the same mapping panel.

## Fixed context

The profile identity, categories, labels, internal values, save state, About me note, privacy message, and navigation destinations stay identical. This is a presentation and interaction experiment only.

## Review questions

1. Can a user express a meaningful trip preference in one or two clicks?
2. Does the mapping panel make the internal contract understandable without exposing implementation jargon as the primary UI?
3. Is the profile useful both on first setup and for a quick correction before a new trip?
4. Does the panel make it obvious which information is durable profile context versus a one-trip exception?
