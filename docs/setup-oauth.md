# Setting up OAuth login for the hosted app

This walkthrough enables **Sign in with Google** and **Sign in with GitHub**
for the Chainlit web app. Login is **fully optional** — visitors who don't
sign in still get a persistent identity via a long-lived guest cookie, so
their preferences and trip history are preserved across sessions on the
same browser.

## Why OAuth + guest cookies

Two parallel identity tracks:

| Track       | Identifier format        | Persistence                                  |
|-------------|--------------------------|----------------------------------------------|
| OAuth login | `google-<sub>` / `github-<id>` | Cross-device, cross-browser (Cosmos DB) |
| Guest cookie| `guest-<uuid>`           | Same browser only, 1-year cookie (Cosmos DB) |
| No cookie   | Chainlit session id      | Single tab (ephemeral, legacy fallback)      |

All three flow into `multiagent.user_context.set_user_id`, so the agent's
continuous-learning tools (`update_user_profile`, `add_family_member`, …)
write to the right per-user document in Cosmos.

## Prerequisites

1. The app is already deployed (`https://multiagent-app-<suffix>.<env>.eastus2.azurecontainerapps.io`).
   Note your exact FQDN — you'll need it for the OAuth redirect URI.
2. You have `gh` CLI authenticated for `munishgoyal1/multiagent` and `az` logged in.

## Step 0 — Generate the auth secret (REQUIRED)

OAuth and the guest-cookie flow are both gated behind `CHAINLIT_AUTH_SECRET`.
If this isn't set, the app behaves exactly like before (per-session id only).

```powershell
$secret = python -c "import secrets; print(secrets.token_urlsafe(32))"
gh secret set CHAINLIT_AUTH_SECRET --body $secret
```

## Step 1 — Google OAuth client

1. Go to <https://console.cloud.google.com/apis/credentials>.
2. **Create credentials → OAuth client ID → Web application**.
3. Name it `multiagent-trip-planner`.
4. **Authorized redirect URI** (exact match, including the trailing path):
   ```
   https://multiagent-app-<your-suffix>.<env>.eastus2.azurecontainerapps.io/auth/oauth/google/callback
   ```
   Replace the FQDN with your actual one from the Azure portal or:
   ```powershell
   az containerapp show -n multiagent-app-<suffix> -g rg-multiagent-trip-planner --query properties.configuration.ingress.fqdn -o tsv
   ```
5. Copy the **Client ID** and **Client secret**.
6. Store them as GitHub secrets:
   ```powershell
   gh secret set OAUTH_GOOGLE_CLIENT_ID --body "<client-id>"
   gh secret set OAUTH_GOOGLE_CLIENT_SECRET --body "<client-secret>"
   ```

## Step 2 — GitHub OAuth client

1. Go to <https://github.com/settings/developers> → **New OAuth App**.
2. Application name: `Multiagent Trip Planner`.
3. Homepage URL: your Container App FQDN.
4. **Authorization callback URL**:
   ```
   https://multiagent-app-<your-suffix>.<env>.eastus2.azurecontainerapps.io/auth/oauth/github/callback
   ```
5. Click **Register application** → **Generate a new client secret**.
6. Store secrets:
   ```powershell
   gh secret set OAUTH_GITHUB_CLIENT_ID --body "<client-id>"
   gh secret set OAUTH_GITHUB_CLIENT_SECRET --body "<client-secret>"
   ```

## Step 3 — Trigger redeploy

The next push to `master` (or a manual workflow run) picks up the new
secrets and bakes them into the Container App.

```powershell
gh workflow run "Build & Deploy to Azure Container Apps"
```

## Step 4 — Verify

Open the app URL. You should see Chainlit's login screen with both
**Continue with Google** and **Continue with GitHub** buttons, plus the
option to continue as a guest.

## Opting out (no login at all)

Don't set `CHAINLIT_AUTH_SECRET` (or any of the OAuth secrets) and the app
falls back to the original behavior: each browser session gets a Chainlit-
generated id, no login UI, no guest cookie. Useful for purely local dev.

## Disabling one provider but not the other

Leave one provider's secrets unset. Chainlit hides login buttons for
providers whose env vars are missing.

## Facebook login — not currently wired

Chainlit's built-in OAuth providers (as of 1.3) cover Google, GitHub,
Microsoft Entra ID, Okta, AWS Cognito, Auth0, Descope and Apple — but
**not Facebook**. Adding it would require a custom Starlette route that
runs Facebook's OAuth 2.0 flow with `authlib` and synthesizes a
`cl.User`. We can ship that in a follow-up if needed; for now, GitHub is
wired in as the second social provider since it's natively supported.

## Local development with OAuth

Add the same env vars to your local `.env` (or shell):

```
CHAINLIT_AUTH_SECRET=<same as prod, or a separate dev secret>
OAUTH_GOOGLE_CLIENT_ID=<dev client id>
OAUTH_GOOGLE_CLIENT_SECRET=<dev client secret>
OAUTH_GITHUB_CLIENT_ID=<dev client id>
OAUTH_GITHUB_CLIENT_SECRET=<dev client secret>
```

Use a **separate Google/GitHub OAuth app** for local dev with redirect
URI `http://localhost:8000/auth/oauth/google/callback` (and the GitHub
equivalent). Don't reuse production credentials.

Run: `chainlit run src/multiagent/web/app.py --port 8000`.

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| "redirect_uri_mismatch" from Google | The URI in Google Console must match the deployed FQDN exactly, including `https://` and `/auth/oauth/google/callback`. |
| No login screen appears | `CHAINLIT_AUTH_SECRET` not set on the Container App. Run `az containerapp show … --query properties.template.containers[0].env` and confirm it's present. |
| Guest cookie identity changes after each visit | Browser is blocking cookies for the Container App domain, or the user is in private/incognito mode. |
| User logs in but sees no past trips | Cosmos document was created under their old `guest-<uuid>` id. Migration of guest → logged-in identity is not implemented yet; tracked as a follow-up. |

---

# Google OAuth for the React SPA (`frontend/`)

The standalone SPA talks to the plain FastAPI backend (`api.py`), not
Chainlit, so it has its own OAuth flow in `src/multiagent/web/oauth.py`. It
deliberately **reuses the exact same env vars and identifier scheme** as the
Chainlit app — `OAUTH_GOOGLE_CLIENT_ID`, `OAUTH_GOOGLE_CLIENT_SECRET`,
`CHAINLIT_AUTH_SECRET`, and the `google-<sub>` user id — so a user who signs
in with Google resolves to the **same identity on both UIs**, and their
preferences and trips carry across with zero migration. No extra Python
dependencies (stdlib + the existing `httpx`).

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

The session cookie is signed with HMAC-SHA256 using `CHAINLIT_AUTH_SECRET`
(or `WEB_SESSION_SECRET` as a fallback).

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
  OAUTH_REDIRECT_BASE=https://your-app.example.com/api
  # register https://your-app.example.com/api/auth/callback/google
  ```

If `OAUTH_REDIRECT_BASE` is unset, the callback URI is derived from the
incoming request — fine when the SPA and API already share an origin.

## Local dev steps

1. Create (or reuse) a Google OAuth **Web application** client and add the
   redirect URI `http://localhost:5173/api/auth/callback/google`.
2. Put these in your `.env` (or shell):
   ```
   CHAINLIT_AUTH_SECRET=<any random string; reused as the session signing key>
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

