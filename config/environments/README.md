# Environment configuration

These checked-in profiles are the source of truth for non-secret runtime and
deployment configuration:

- `local.env` applies to primary local development and sandboxes.
- `canary.env` applies to canary deployments.
- `prod.env` applies to production deployments.

Ignored `.env`, `.env.canary`, and `.env.prod` files contain secrets only. Their
values overlay the corresponding profile. Existing non-secret values in those
files remain supported during migration, but new non-secret settings must be
added to all three profiles. Process environment variables remain the highest
precedence for local runtime; explicit deployment script arguments remain the
highest precedence for deployments.

`.env.example` is intentionally a secrets template, not a configuration
superset. The three profiles have the same key set so environment differences
are visible in review, and tests fail if the sets drift or a known secret enters
a checked-in profile.
`TRIPPLANNER_FLIGHT_RECORDER=0` is the default master switch for private diagnostic
recording and automatic local trip archives. Set it to `1` in the environment's
profile and restart its backend to enable recording; reset to `0` and restart to
remove capture work. `TRIPPLANNER_DEBUG_STORE` remains an additional local archive
switch, and hosted raw archives remain disabled. Verbose recording cannot enable
the recorder by itself. Existing history and ordinary logs/accounting are retained.
