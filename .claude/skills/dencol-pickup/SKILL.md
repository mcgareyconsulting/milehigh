---
name: dencol-pickup
description: Record a vendor part pick-up against a job release. Use when the user asks to log/update a pick-up for a release (e.g. "update 380-456 Dencol info", "log the Dencol pickup for 280-235"). Finds the related vendor email, then records it in Brain (which creates the Trello card).
---

# Dencol Pick-Up Skill

Orchestrates a semi-deterministic pick-up: **you** find the right vendor email and
identify the release; **Brain** does the deterministic part (writes the `PickupOrder`,
the audit event, and queues the Trello card via its outbox). Keep the fuzzy work here
and hand structured content to Brain.

## When to use
The user references logging/updating a vendor pick-up for a specific job release, e.g.:
- "update 380-456 Dencol information"
- "log the Dencol pick-up for 280-235"
- "BananaBoy, record the pickup email for 412-V3"

## Inputs to extract from the request
- **job** and **release** — the user almost always names it (e.g. "380-456" → job 380, release "456"; "412-V3" → job 412, release "V3"). This is authoritative; do NOT rely on parsing the email subject when the user gave the release.
- **vendor** — default "Dencol" unless the user says otherwise.

## Steps
1. **Parse the release** from the request into `job` + `release`. If ambiguous, ask the user to confirm before proceeding.
2. **Find the vendor email.** Search the mailbox for the pick-up email related to this release/vendor.
   - Gmail (now): use the Gmail MCP search (`mcp__claude_ai_Gmail__search_threads`) with a query like
     `from:dencol OR subject:("380-456" OR "380 456" OR Dencol) newer_than:30d`, then `get_thread` to read the best match.
   - Microsoft (later): same step via the Graph/Outlook tool — only this retrieval step changes; everything below stays identical.
   - If multiple plausible emails match, show the candidates and let the user pick. If none match, report that and stop (don't fabricate).
3. **Extract** from the chosen email: `subject`, `from`, `to`, plain-text `body` (the full traceback), the provider `message_id`, and the `received_at` date.
4. **POST to Brain** — this single call records the DB rows AND triggers the Trello card:
   ```
   POST {BRAIN_BASE_URL}/brain/pickup/ingest
   Authorization: Bearer {BRAIN_SERVICE_TOKEN}
   Content-Type: application/json

   {
     "job": 380, "release": "456", "vendor": "Dencol",
     "subject": "<email subject>", "from": "<sender>", "to": "<recipient>",
     "body": "<full email text>",
     "message_id": "<provider message id>",     // idempotency key — reuse the real one
     "received_at": "2026-05-26T15:00:00Z"        // controls the card's 11:59pm MT due date
   }
   ```
5. **Interpret the response** and report to the user:
   - `{"status":"recorded", "pickup_order_id":N, "event_id":M}` → success. The Trello card (PU Dencol: …, in Shipping planning, with the always-on members + the release's PM) is queued and created by Brain's outbox within seconds.
   - `{"status":"duplicate", ...}` → this exact email was already recorded (message_id seen). No action needed.
   - `{"status":"unmatched", ...}` → no release `job-release` exists in Brain. Surface this; the release may be wrong or not yet in the job log.
   - 400 → you sent neither job+release nor a parseable subject.

## Reading back / rundown
To answer "give me a rundown on 280-235" (or to show the user what changed before/after a pickup),
GET the consolidated view — release + changelog + pick-ups in one call:
```
GET {BRAIN_BASE_URL}/brain/release/<job>/<release>/rundown
Authorization: Bearer {BRAIN_SERVICE_TOKEN}
```
Returns `{ "release": {...}, "events": [...newest first...], "pickups": [...with email audit...] }`.
Use it to summarize status, surface the related Dencol email, and confirm a pickup landed.

## Notes
- **Two ways in.** This skill is the *on-demand* path (you find the email and POST it). The *hands-off* path is an inbound-email webhook: the user forwards a vendor email to a CloudMailin address, which POSTs it to `POST {BRAIN_BASE_URL}/brain/pickup/inbound-email` (shared-secret guarded) and runs the same recording pipeline automatically. Both converge on the same `PickupOrder` + Trello card, and both are idempotent on the email's `message_id`, so they're safe to mix.
- **Idempotency**: always pass the real provider `message_id` so re-running the skill on the same email is a safe no-op.
- **Provider-agnostic**: Brain never touches the user's mailbox — only step 2 (your retrieval) changes when moving Gmail → Microsoft. Brain's own ingestion is push-based via the inbound webhook (no polling, no OAuth).
- **Don't create Trello cards yourself.** Brain owns Trello via its outbox (retry/idempotency). Your job ends at the `ingest` POST.
- For testing without a live board, Brain can run with `TRELLO_MOCK=1` (simulates the card); the API responses are identical.
- Config the caller needs: `BRAIN_BASE_URL` and `BRAIN_SERVICE_TOKEN`.
