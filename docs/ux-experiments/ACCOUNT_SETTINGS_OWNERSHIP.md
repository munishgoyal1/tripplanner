# Experiment: Account and settings ownership

## Meta

- Owner: Munish Goyal
- Date started: 2026-08-01
- Status: testing
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
- Keep the Analytics preferences destination interactive in every option.
- Preserve authentication, analytics collection, storage, privacy APIs, trip
  controls, pane controls, and workspace content as context only.

## Variants

- **A - Unified account menu:** one avatar owns identity, travel profile,
  analytics, privacy/data, and sign-out. Removes the separate gear.
- **B - Clear account/settings split:** Profile owns only identity and sign-out;
  Settings owns travel profile, analytics, and privacy/data with no duplication.
- **C - Account settings hub:** one labeled identity trigger opens a larger,
  sectioned sheet for all person-level controls.

## Current recommendation

Start evaluation with **A - Unified account menu**. It removes the redundant
trigger with the smallest footprint and keeps person-level settings in one
predictable location. This recommendation is not implementation approval.

## Independent defect fix

The production Analytics preferences command now opens an explicit preference
surface even when analytics collection is not configured. The user can save a
future preference, while collection remains disabled without a measurement ID.

## Decision

- Decision: pending owner evaluation
- Production redesign status: not implemented
- Next action: compare all three interactive options and save one handoff