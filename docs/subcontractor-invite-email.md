# Subcontractor invite email — Carmen mailbox + PM CC

Subcontractor invite emails send **app-only, as the shared Carmen Miranda
persona mailbox** (`Config.CARMEN_MAILBOX`, default `carmen_ai@mhmw.com`) via
`app/microsoft/mailer.py`'s `send_mail()`. The admin/PM who triggered the
invite (or resend) is **CC'd**, not the sender — they keep a copy for their
own System-of-Record without owning the send identity.

Two earlier designs were rejected:
- **Send as bb@mhmw.com** — rejected because that mailbox's inbox is wired to
  ingestion pollers (supplier orders, meeting bot, etc.); a subcontractor
  hitting "reply" would dump into that pipeline as unrelated bronze data.
- **Send as the individual signed-in admin** — rejected because it required a
  brand-new `ApplicationAccessPolicy` scope group covering every admin's own
  mailbox, and only worked for admins whose Brain login is their real
  `@mhmw.com` address. CC'ing the PM gets the same "they see it happened"
  outcome without either problem.

## Azure status

`carmen_ai@mhmw.com` is already provisioned and currently shares the same
`ApplicationAccessPolicy` scope as `bb@mhmw.com` (confirmed 2026-07-25) — so
**no new Azure setup is required** for this feature. If that policy is ever
split so Carmen's mailbox is scoped independently, re-verify with:

```powershell
Test-ApplicationAccessPolicy -Identity carmen_ai@mhmw.com -AppId <AZURE_CLIENT_ID>   # expect Granted
```

## Remaining step

- [ ] **Smoke test** (app running): invite a real test-inbox subcontractor
      email from `/subcontractors` and confirm the email arrives from
      `carmen_ai@mhmw.com` with the inviting admin CC'd.

## Note on the Carmen Miranda rename

This mailbox choice is independent of the broader BB → Carmen Miranda rebrand
tracked in `docs/carmen-miranda-rename-scope.md` (which is about renaming
`bb@mhmw.com`'s role, tables, env vars, etc.). This feature just picks
`carmen_ai@mhmw.com` as the send identity for a brand-new capability that has
no legacy tie to `bb@mhmw.com` — it isn't a statement about that rename's
progress or scope.
