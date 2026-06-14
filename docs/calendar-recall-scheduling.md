# Calendar → Recall scheduling

Invite **bb@mhmw.com** to a Teams meeting and a Recall notetaker bot ("BB") joins
on its own at the meeting's start time. The calendar is the scheduling UI — no
"dispatch now" button, no deriving a start time from an opaque Teams link.

We deliberately do **not** use Recall's own Calendar-V2 integration — that connects
bb's calendar to Recall via delegated OAuth, re-introducing the consent/exposure wall
the app-only approach exists to avoid. We poll Graph ourselves and dispatch bots
directly.

## How it works

1. A poller (`calendar_recall_poll`, every `RECALL_CALENDAR_POLL_MINUTES`, default 5)
   reads the bb mailbox's calendar **as the application** (app-only Graph, same
   `AZURE_*` app registration as the bb-email mail ingestion), over a window of
   `[now − 5m, now + RECALL_CALENDAR_LOOKAHEAD_MINUTES]`. `calendarView` expands
   recurring meetings into concrete instances.
2. Events carrying a Teams join URL (`onlineMeeting.joinUrl`, then `onlineMeetingUrl`,
   then a Teams link in the body) are scheduled: `recall.dispatch_bot(join_url,
   join_at=start − RECALL_CALENDAR_JOIN_LEAD_SECONDS)`. Recall holds the bot until
   `join_at` and **guarantees an on-time join when `join_at` is ≥10 min out** — which
   is why the lookahead is an hour: a meeting bb is invited to in advance gets its bot
   dispatched ~an hour early. Cancelled/declined events and non-Teams events are
   skipped. A meeting already in progress (start just past) joins immediately.
3. A `source='recall'`, `bot_status='scheduled'` `Meeting` row is persisted with
   `occurred_at` = the meeting start and `calendar_event_id` = the Graph event id.
   That id is the **idempotency key** — one event schedules exactly one bot across
   polls.
4. **Reconciliation** (each poll, only while `bot_status='scheduled'` — a live bot is
   never touched): if the event was **cancelled/declined**, the scheduled bot is
   deleted (`DELETE /bot/{id}`) and the meeting marked `cancelled`; if the **start
   moved**, the old bot is deleted and a new one dispatched for the new time. If the
   bot has already begun joining (`cannot_delete_bot`), it's left live.
5. Post-meeting, the existing pull/transcript/extract pipeline takes over unchanged
   (the `recall-webhook` receiver updates `bot_status`, pulls the transcript, and the
   "Generate to-do list" flow mines it).

## Testing the live flow

Don't wait for the 5-minute poll — trigger it on demand (admin):

```
POST /brain/meetings/calendar/poll            # run it for real
POST /brain/meetings/calendar/poll  {"dry_run": true}   # classify only, dispatch nothing
```

`dry_run` returns `{scheduled, rescheduled, cancelled, skipped, events}` for what it
*would* do — invite bb to a test Teams meeting, hit the endpoint, and confirm it's
seen before flipping anything on.

## Known limitation

An event **hard-deleted** from the calendar (vs. cancelled) stops appearing in
`calendarView`, so its already-scheduled bot isn't retracted — it joins an empty room
and produces a short recording. Cancelling (the normal Outlook action) is handled.

## Config (`app/config.py`)

| Var | Default | Meaning |
|---|---|---|
| `RECALL_CALENDAR_ENABLED` | `0` | Master switch; poller is a no-op until `1`. |
| `RECALL_CALENDAR_MAILBOX` | `bb@mhmw.com` | Whose calendar to watch. |
| `RECALL_CALENDAR_POLL_MINUTES` | `5` | Poll cadence (must be `<` lookahead). |
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
