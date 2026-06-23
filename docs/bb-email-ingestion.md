# BB Email Ingestion — status & resume points

First concrete ingestion source for the Hive Mind data lake: mailboxes →
`raw_source_records` (bronze). Built on branch `feature/bb-email`.

**Current status:** code complete + tested (18 lake/microsoft tests green).
**Blocked on:** client consent for the Azure infrastructure (admin must grant
application permissions + create the access-policy group). Nothing has been
applied to sandbox/prod yet.

---

## Architecture (settled)

- **Backbone = app-only (application permissions).** Connector reads via
  `app/microsoft/graph_app_client.py::get_app_token` (client-credentials, needs
  `AZURE_CLIENT_SECRET`). No per-user tokens to maintain.
- **Mailbox set is admin-governed by a security group.** With `BB_INGEST_GROUP_ID`
  set, the poller discovers members via Graph `/groups/{id}/transitiveMembers` and
  ingests each → onboarding a mailbox = admin adds it to the group. Fallbacks:
  `BB_MAILBOXES` (comma list) → single `BB_MAILBOX`.
- **Full mailbox content**, per-mailbox watermark (`LakeIngestState(source, account)`),
  one mailbox failing doesn't abort the rest.
- **Delegated device-code path kept as a future self-serve opt-in** (`graph_delegated.py`,
  `MicrosoftDelegatedToken`, `scripts/link_bb_mailbox.py`) — unused by the backbone.
  `graph_get` has a pluggable `token_getter` so both models coexist.

Why app-only over delegated: tenant has **user consent disabled**, so an admin is
required either way; app-only is the more robust org-data-lake structure.

---

## TODO — blocked on client/admin (Azure infra)

- [ ] **Admin: grant application permissions** on the app registration —
      Graph → Application permissions → `Mail.ReadWrite`, `Mail.Send`,
      `GroupMember.Read.All` (the last only for group auto-discovery; skip it and
      use `BB_MAILBOXES` if a directory-read perm is unwelcome) → **Grant admin consent**.
- [ ] **Admin: confirm a client secret** exists; capture its value → `AZURE_CLIENT_SECRET`.
- [ ] **Admin: create the mailbox group + access policy** (Exchange Online PowerShell):
      ```powershell
      New-DistributionGroup -Name "BananaBoy-Mailboxes" -Type Security
      Add-DistributionGroupMember -Identity "BananaBoy-Mailboxes" -Member bb@mhmw.com
      New-ApplicationAccessPolicy -AppId <AZURE_CLIENT_ID> `
        -PolicyScopeGroupId BananaBoy-Mailboxes@mhmw.com -AccessRight RestrictAccess `
        -Description "Banana Boy may access only this group's mailboxes"
      Test-ApplicationAccessPolicy -Identity bb@mhmw.com -AppId <AZURE_CLIENT_ID>   # expect Granted
      ```
- [ ] **Capture group object ID** (Entra → Groups → BananaBoy-Mailboxes → Overview) → `BB_INGEST_GROUP_ID`.
- [ ] **Set `.env`** (`/Users/danielmcgarey/Desktop/MHMW/milehigh/.env`):
      `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`,
      `BB_INGEST_GROUP_ID`, `BB_MAIL_INGEST_ENABLED=1`.

## RESUME — once consent lands (engineering)

1. **Apply the migration** (creates `raw_source_records` + `lake_ingest_state`):
   ```bash
   ENVIRONMENT=sandbox .venv/bin/python migrations/add_lake_tables.py
   ```
   (`db.create_all()` also creates them on app boot; the script is the explicit path.)
2. **Smoke test on-demand** (app running, as an admin user):
   ```
   POST /lake/ingest/mail/pull  {"mailbox":"bb@mhmw.com"}
   POST /lake/ingest/mail/pull  {"mailbox":"bb@mhmw.com","query":"RFI"}
   ```
   Confirm `raw_source_records` rows with `source="m365_mail"`.
3. **Verify the scheduled poll** lands mail every `BB_MAIL_POLL_MINUTES` (default 15)
   and that group discovery returns the expected mailbox set.
4. **Verify access-policy scoping**: `Test-ApplicationAccessPolicy` denies a non-group mailbox.

## Backlog — next increments (not blocked, just not built)

- [ ] **Send path** — `graph_post` in `graph_app_client.py` + an `outlook_send` helper
      (perms already requested: `Mail.Send`). Enables BB to draft/reply.
- [ ] **Silver normalization** — bronze `raw_source_records` → `core_communication` /
      participants / segments / `core_reference` (entity-linking to releases/submittals/projects).
- [ ] **BB chat tool** — wire `m365_mail.pull(query=...)` into the Banana Boy agent so
      "read the email I forwarded you" pulls fresh + cites results.
- [ ] **Attachment handling** — currently only `external_pointer` (webLink) is stored;
      fetch/stash attachments to R2/S3 if media ownership is needed.
- [ ] **(Optional) Self-serve opt-in** — turn on the delegated device-code path for
      individuals: apply `migrations/add_microsoft_delegated_tokens.py`, set
      "Allow public client flows", run `scripts/link_bb_mailbox.py`.

---

## Map of what's in the tree

| File | Purpose |
|------|---------|
| `app/models.py` | `RawSourceRecord`, `LakeIngestState`, `MicrosoftDelegatedToken` |
| `app/microsoft/graph_app_client.py` | app-only token + shared `graph_get(token_getter=...)` |
| `app/microsoft/graph_delegated.py` | delegated device-code path (future opt-in) |
| `app/lake/ingest/m365_mail.py` | `resolve_mailboxes`/`pull`/`poll` (+ `_normalize`/`_land`) |
| `app/lake/routes.py` | `lake_bp`, admin-only `POST /lake/ingest/mail/pull` |
| `app/__init__.py` | registers `lake_bp` + `bb_mail_poll` scheduler job (gated by `BB_MAIL_INGEST_ENABLED`) |
| `app/config.py` | `BB_MAILBOX`, `BB_MAILBOXES`, `BB_INGEST_GROUP_ID`, `BB_MAIL_POLL_MINUTES`, `BB_MAIL_INGEST_ENABLED` |
| `migrations/add_lake_tables.py` | bronze + watermark tables (idempotent) |
| `migrations/add_microsoft_delegated_tokens.py` | delegated token table (only for opt-in path) |
| `scripts/link_bb_mailbox.py` | one-time device-code link (only for opt-in path) |
| `tests/lake/`, `tests/microsoft/` | connector, endpoint, token tests |
