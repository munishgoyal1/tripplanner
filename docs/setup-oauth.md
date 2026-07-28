# Setting up Google OAuth login for the hosted app

This walkthrough enables **Sign in with Google** for the React SPA. Login is
**fully optional** — visitors who don't sign in still get a persistent
identity via a long-lived guest id stored in their browser, so their
preferences and trip history are preserved across sessions on the same
browser.

## Why OAuth + guest identity

Two parallel identity tracks:

| Track       | Identifier format        | Persistence                                  |
|-------------|--------------------------|----------------------------------------------|
| OAuth login | `google-<sub>`           | Cross-device, cross-browser (Cosmos DB)      |
| Guest id    | `web-<uuid>`             | Same browser only (localStorage)             |

Both flow into `tripplanner.user_context.set_user_id`, so the agent's
continuous-learning tools (`update_user_profile`, `add_family_member`, …)
write to the right per-user document in Cosmos.

The SPA talks to the FastAPI backend (`api.py`), which owns the OAuth flow in
`src/tripplanner/web/oauth.py` — stdlib + the existing `httpx`, no extra deps.
It degrades gracefully: with the env vars unset, the **Sign in with Google**
button is hidden and the SPA falls back to name / anonymous sign-in.

## Endpoints (FastAPI)

| Route | Purpose |
|-------|---------|
| `GET /auth/config` | `{ "google": true/false }` — tells the SPA whether to show the button. |
| `GET /auth/login/google?redirect=/` | Redirects the browser to Google's consent screen. |
| `GET /auth/callback/google` | Google returns here; the backend exchanges the code, sets a signed HttpOnly `mg_session` cookie, and bounces back to the SPA. |
| `GET /auth/me` | Current session `{ authenticated, user_id, display_name, email, picture }`. |
| `POST /auth/logout` | Clears the session cookie. |

The session cookie is signed with HMAC-SHA256 using `WEB_SESSION_SECRET`
(the `CHAINLIT_AUTH_SECRET` env var is also still read as a fallback for
back-compat).

## Step 0 — Generate the session secret (REQUIRED for login)

OAuth is gated behind the signing secret. If this isn't set, the app behaves
exactly like before (anonymous / name-only identity).

```powershell
$secret = python -c "import secrets; print(secrets.token_urlsafe(32))"
Add-Content .env "WEB_SESSION_SECRET=$secret"
```

The guarded deployment scripts load `.env`; do not commit it.

## Step 1 — Google OAuth client

1. Go to <https://console.cloud.google.com/apis/credentials>.
2. **Create credentials → OAuth client ID → Web application**.
3. Name it `tripplanner`.
4. Add the hosted **Authorized redirect URIs** (exact matches):
   ```
   https://<canary-fqdn>/api/auth/callback/google
   https://aitripplanner.co/api/auth/callback/google
   ```
   Keep the generated production Azure callback registered temporarily for
   rollback access:
   ```
   https://prod-app-f3ddjudq2rdt4.redglacier-42f3888f.eastus2.azurecontainerapps.io/api/auth/callback/google
   ```
   Find the current FQDNs with:
   ```powershell
   az containerapp list -g rg-tripplanner-canary --query "[?starts_with(name, 'canary-app-')].properties.configuration.ingress.fqdn" -o tsv
   az containerapp list -g rg-tripplanner-prod --query "[?starts_with(name, 'prod-app-')].properties.configuration.ingress.fqdn" -o tsv
   ```
5. Copy the **Client ID** and **Client secret** into the uncommitted `.env` file:
   ```powershell
   Add-Content .env "OAUTH_GOOGLE_CLIENT_ID=<client-id>"
   Add-Content .env "OAUTH_GOOGLE_CLIENT_SECRET=<client-secret>"
   ```

## Step 2 — Deploy through canary

The manual GitHub Actions workflow only publishes an image. Apply OAuth
configuration and deploy through the guarded canary script:

```powershell
.\infra\deploy-canary.ps1
```

Verify canary before requesting production approval. Production promotion uses
`.\infra\deploy-prod.ps1` and the exact image already tested in canary.

## Step 3 — Verify

Open the app URL, then the account menu → **Sign in with Google**. After
consent you should return signed in, with your Google display name shown.

## Opting out (no login at all)

Leave the signing secret and the OAuth secrets unset: the SPA hides the
login button and each browser gets a persistent `web-<uuid>` guest id. Useful
for purely local dev.

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| "redirect_uri_mismatch" from Google | The URI in Google Console must match exactly, including `https://` and `/api/auth/callback/google`. |
| Sign-in button missing | The signing secret or OAuth client env vars aren't set on the Container App. |
| User logs in but sees no past trips | Cosmos document was created under their old `web-<uuid>` id. Migration of guest → logged-in identity is not implemented yet; tracked as a follow-up. |

---

# Google OAuth — configuration details

The SPA's OAuth flow lives in `src/tripplanner/web/oauth.py`. It uses the
`google-<sub>` user id so a user who signs in with Google resolves to a stable
identity, and their preferences and trips carry across devices.

## Redirect URI — the one thing you must get right

Set `OAUTH_REDIRECT_BASE` to the public base that fronts `/auth/...`, and
register `<OAUTH_REDIRECT_BASE>/auth/callback/google` in the Google console.

* **Local dev** (everything stays same-origin through the Vite proxy on
  `:5173`, which avoids cross-origin cookie headaches):
  ```
  OAUTH_REDIRECT_BASE=http://localhost:5173/api
  ```
  Register this exact redirect URI in Google:
  ```
  http://localhost:5173/api/auth/callback/google
  ```
* **Production** (single origin serving SPA + API):
  ```
   OAUTH_REDIRECT_BASE=https://aitripplanner.co/api
   # register https://aitripplanner.co/api/auth/callback/google
  ```

If `OAUTH_REDIRECT_BASE` is unset, the callback URI is derived from the
incoming request — fine when the SPA and API already share an origin.

## Local dev steps

1. Create (or reuse) a Google OAuth **Web application** client and add the
   redirect URI `http://localhost:5173/api/auth/callback/google`.
2. Put these in your `.env` (or shell):
   ```
   WEB_SESSION_SECRET=<any random string; reused as the session signing key>
   OAUTH_GOOGLE_CLIENT_ID=<client id>
   OAUTH_GOOGLE_CLIENT_SECRET=<client secret>
   OAUTH_REDIRECT_BASE=http://localhost:5173/api
   ```
3. Run the SPA stack: `scripts\dev-spa.ps1` (backend on `:8000`, Vite on
   `:5173`). Open <http://localhost:5173>, click the account menu →
   **Sign in with Google**.

## Production CORS note

Cookie-based sessions need credentials, which browsers forbid alongside the
`*` CORS wildcard. When the SPA is on a **different origin** from the API,
set explicit origins so credentials are allowed:
```
WEB_ALLOWED_ORIGINS=https://your-spa.example.com
```
When the SPA and API share an origin (e.g. served behind one Container App),
no change is needed — requests are same-origin and CORS doesn't apply.


