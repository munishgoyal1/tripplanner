# Experiment: Account and settings ownership

## Meta

- Owner: Munish Goyal
- Date started: 2026-08-01
- Status: Implemented - To be reviewed
- Date implemented: 2026-08-02
- Lab: `http://127.0.0.1:5175/account-settings.html`

## Problem

The desktop command bar exposes separate Account and Travel preferences icons,
while the Account menu repeats preference and privacy destinations. Analytics
preferences also appeared inert when analytics collection was not configured
because its event could not render the consent surface.

## Scope

- Compare ownership and grouping of identity, travel profile, analytics,
  privacy/data controls, and sign-out.
- Compare one versus two command-bar triggers and compact menu versus settings hub.
- Keep Travel Profile, Analytics, and Privacy and Data complete and interactive
  in every option, including saved defaults, history/export controls, and
  destructive-action confirmation states.
- Preserve authentication, analytics collection, storage, privacy APIs, trip
  controls, pane controls, and workspace content as context only.

## Variants

- **A - Unified account menu:** one avatar owns identity, travel profile,
  analytics, privacy/data, and sign-out. Removes the separate gear.
- **B - Clear account/settings split:** Profile owns only identity and sign-out;
  Settings owns travel profile, analytics, and privacy/data with no duplication.
- **C - Account settings hub:** one labeled identity trigger opens a larger,
  sectioned sheet for all person-level controls.

## Selected direction

**C - Account settings hub** was selected and promoted to production. One
labeled identity command opens a right-side sheet with Profile and Sign-in,
Travel Profile, Analytics preferences, and Privacy and Data sections.

## Inspectable destination detail

- **Profile and Sign-in:** verified identity, connected Google account, current
  web and mobile sessions, display-name editing, provider handoff, and reviewed
  sign-out across all devices.
- **Travel Profile:** home base and airport, trip pace, stay and transport
  style, food preferences, usual travel party, locale, accessibility, comfort,
  save state, and the boundary between reusable defaults and trip overrides.
- **Analytics:** current consent, the event categories included, the personal
  data excluded, and behavior when collection is not configured.
- **Privacy and Data:** saved-data inventory, personalization history, retention,
  portable export, separate history deletion, and permanent account deletion.

## Independent defect fix

The production Analytics preferences command now opens an explicit preference
surface even when analytics collection is not configured. The user can save a
future preference, while collection remains disabled without a measurement ID.

## Decision

- Decision: **C - Account settings hub**
- Production redesign status: Implemented on 2026-08-02; awaiting owner review
- Production scope: labeled identity trigger, sectioned account sheet, existing
  Google/local identity flows, persisted Travel Profile, analytics consent, and
  established privacy deletion actions.
- Grounding note: the Lab's illustrative session inventory and portable export
  were not promoted because production does not currently expose those APIs.