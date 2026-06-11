# Calendar → Recall scheduling

Invite **bb@mhmw.com** to a Teams meeting and a Recall notetaker bot ("BB") joins
on its own at the meeting's start time. The calendar is the scheduling UI — no
"dispatch now" button, no deriving a start time from an opaque Teams link.

## How it works

1. A poller (`calendar_recall_poll`, every `RECALL_CALENDAR_POLL_MINUTES`) reads the
   bb mailbox's calendar **as the application** (app-only Graph, same `AZURE_*` app
   registration as the bb-email mail ingestion), over a window of
   `[now, now + RECALL_CALENDAR_LOOKAHEAD_MINUTES]`. `calendarView` expands recurring
   meetings into concrete instances.
2. Events carrying a Teams `joinUrl` are scheduled: `recall.dispatch_bot(join_url,
   join_at=start − RECALL_CALENDAR_JOIN_LEAD_SECONDS)`. Recall holds the bot until
   `join_at`, so we can dispatch the moment the event appears.
3. A `source='recall'`, `bot_status='scheduled'` `Meeting` row is persisted with
   `occurred_at` = the meeting start and `calendar_event_id` = the Graph event id.
   That id is the **idempotency key** — one event schedules exactly one bot across
   polls. An already-running meeting (start in the past but inside the window) joins
   immediately (`join_at=None`).
4. Post-meeting, the existing pull/transcript/extract pipeline takes over unchanged
   (the `recall-webhook` receiver updates `bot_status`, pulls the transcript, and the
   "Generate to-do list" flow mines it).

## Config (`app/config.py`)

| Var | Default | Meaning |
|---|---|---|
| `RECALL_CALENDAR_ENABLED` | `0` | Master switch; poller is a no-op until `1`. |
| `RECALL_CALENDAR_MAILBOX` | `bb@mhmw.com` | Whose calendar to watch. |
| `RECALL_CALENDAR_POLL_MINUTES` | `10` | Poll cadence (must be `<` lookahead). |
| `RECALL_CALENDAR_LOOKAHEAD_MINUTES` | `60` | How far ahead to schedule. |
| `RECALL_CALENDAR_JOIN_LEAD_SECONDS` | `60` | Join this early before the start. |

Reuses `AZURE_CLIENT_ID` / `AZURE_CLIENT_SECRET` / `AZURE_TENANT_ID` and
`RECALL_API_KEY`.

## Operational prerequisites (admin, one-time)

1. Grant the app registration the **`Calendars.Read` application permission** and
   admin-consent it.
2. Extend (or add) an **`ApplicationAccessPolicy`** scoping the app's Graph access to
   the security group that contains `bb@mhmw.com` — the same group used by the mail
   ingestion. (`New-ApplicationAccessPolicy -AppId <id> -PolicyScopeGroupId <group>
   -AccessRight RestrictAccess`.)
3. Run the migration: `ENVIRONMENT=<env> python migrations/add_calendar_event_id_to_meetings.py`.
4. Set `RECALL_CALENDAR_ENABLED=1`.

## Onboarding a meeting

Invite `bb@mhmw.com` (or forward the calendar invite). Recurring meetings are handled
per-occurrence, so a standing weekly meeting records every week with no further action.
