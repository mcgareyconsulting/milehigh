# Azure App Registration — Outlook OAuth for Banana Boy

This guide creates the Azure (Entra ID) app registration that lets Banana Boy
read a user's Outlook mailbox during a report deep dive. It is **separate**
from the existing `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` registration,
which uses the client-credentials flow against a single fixed mailbox for
OneDrive/Excel polling. This new registration uses delegated per-user OAuth.

You build it once in **your own** Azure tenant. Your client signs in with
their work account from their tenant; no test-user allowlist is required.

---

## 1. Create the registration

1. Go to <https://portal.azure.com> → **Microsoft Entra ID** → **App registrations** → **New registration**.
2. **Name**: `MHMW Banana Boy Outlook` (or similar — visible to users on the consent screen).
3. **Supported account types**: choose one:
   - **Accounts in any organizational directory (Multitenant)** — recommended. Any work/school tenant can sign in.
   - *Only* pick "single tenant" if you want this locked to your own directory.
   - *Avoid* "personal Microsoft accounts" unless you also need to support outlook.com / hotmail.com personal mailboxes.
4. **Redirect URI**: Platform = **Web**, value = the same value you'll set in `MS_REDIRECT_URI`.
   - Local dev: `http://localhost:8000/api/auth/microsoft/callback`
   - Sandbox: `https://<sandbox-host>/api/auth/microsoft/callback`
   - Production: `https://<prod-host>/api/auth/microsoft/callback`
   - You can add multiple redirect URIs later; add all of them on the **Authentication** blade.
5. Click **Register**.

After registration, copy from the **Overview** page:
- **Application (client) ID** → goes into `MS_CLIENT_ID`
- **Directory (tenant) ID** → only needed if you chose single-tenant; otherwise leave `MS_TENANT=common`

---

## 2. Add a client secret

1. **Certificates & secrets** → **Client secrets** → **New client secret**.
2. Description: `banana-boy-outlook`. Expiry: 24 months (or per your policy).
3. Click **Add**, then immediately copy the **Value** column (you cannot see it again).
4. Paste into `.env` as `MS_CLIENT_SECRET`.

---

## 3. Configure API permissions (delegated)

1. **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions**.
2. Add these:
   - `openid`
   - `profile`
   - `email`
   - `offline_access` *(required for refresh tokens — without it the user has to re-consent every hour)*
   - `User.Read`
   - `Mail.Read`
3. Click **Add permissions**.

Do **not** click "Grant admin consent" in your own tenant — that only affects your tenant. Each client tenant consents on first sign-in.

> **Note**: All six scopes above can be user-consented in most tenants — no admin involvement needed. If a client tenant has disabled user consent (common in larger orgs), their IT admin grants tenant-wide consent once via:
> `https://login.microsoftonline.com/{client-tenant-id}/adminconsent?client_id={MS_CLIENT_ID}`

---

## 4. Set environment variables

Add to `.env`:

```
MS_CLIENT_ID=<Application (client) ID from step 1>
MS_CLIENT_SECRET=<Value from step 2>
MS_TENANT=common
MS_REDIRECT_URI=http://localhost:8000/api/auth/microsoft/callback
```

For multi-tenant apps, leave `MS_TENANT=common`. Use `organizations` if you
want to block personal Microsoft accounts. Use a specific tenant GUID only
for single-tenant deployments.

---

## 5. Run the database migration

```
python migrations/add_microsoft_credentials.py
```

This creates the `microsoft_credentials` table. Idempotent — safe to re-run.

---

## 6. Test the link flow

1. Start the backend (`python run.py`) and frontend (`cd frontend && npm run dev`).
2. Log in to MHMW with your password.
3. Visit `http://localhost:5173` and trigger the Outlook link (UI hook is wired in `frontend/src/services/microsoftAuthApi.js` — call `buildMicrosoftLinkUrl(currentPath)` from a "Connect Outlook" button).
4. Sign in with your Microsoft account, consent to the requested scopes.
5. You should land back on the original page with `?outlook_connected=1`.
6. Hit `GET /api/auth/me` — you should see `outlook_linked: true` and your `outlook_email`.

---

## 7. Troubleshooting

| Error code (in `?ms_error=`) | Meaning | Fix |
|---|---|---|
| `not_configured` | `MS_CLIENT_ID` is missing on the server | Set env vars and restart Flask |
| `state_mismatch` / `state_expired` | Session lost or older than 10 min | Just retry |
| `scope_missing` | User unchecked Mail.Read on the consent screen | Ask them to retry and accept |
| `already_linked_other_user` | This Microsoft account is linked to a different MHMW user | Disconnect on the other user, or link a different Microsoft account |
| `AADSTS65001` (in MS error_description) | User has not consented; admin consent required for the tenant | Run the admin consent URL above |
| `AADSTS50011` | Redirect URI mismatch | Add the exact callback URL in Azure → Authentication |

---

## Why this is separate from the OneDrive registration

`app/onedrive/api.py` uses **app-level client credentials** (`AZURE_CLIENT_ID` + `AZURE_CLIENT_SECRET` + `AZURE_TENANT_ID`) against a fixed mailbox to poll a known shared Excel file. That flow uses *application* permissions (no signed-in user) and grants broad access scoped to one configured user.

Outlook deep-dive needs **delegated** permissions (`Mail.Read` as the signed-in user) so each MHMW user only ever reads their own mailbox. Mixing the two on one registration is possible but messy — easier to keep them as separate Azure apps with distinct env vars.
