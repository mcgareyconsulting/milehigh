# #29 — Release assignments and notifications

**Source:** Board item #29 (open / normal / Job Log)
**Author:** Bill O'Neill — 2026-04-07
**Description:** "Lets think about a way to add people to the releases like we are doing on trello. Make it so you can filter by the things you are assigned too. Also need to figure out how to add notifications for each line on the job log for certain task changes. Updating the team and next guy / guys in the line."

---

## Scope decisions

Confirmed with Daniel 2026-04-25:

- **Brain-only feature.** Trello card members are unrelated and out of scope. No bidirectional sync.
- **"Next guy in line" is just whoever you assigned.** No stage→role mapping. Workflow: drafter finishes → adds Tiny as assignee → changes stage to Paint → Tiny gets a bell notification.
- **Trigger events:** `update_stage`, `update_notes`, `update_start_install`, `update_fab_order`.
- **Delivery:** in-app bell only. No email.
- **Doc structure:** one file, phased.

## Existing infrastructure

- `User.trello_id`, `User.first_name`, `User.last_name`, `User.is_active` already populated.
- `Notification` model already drives the bell via `/brain/notifications/unread-count`.
- `ReleaseEvents` already records every stage / notes / fab-order / start-install change with `{from, to}` payload.
- All four trigger actions route through a single call site: `JobEventService.create()`. One hook fans notifications.

---

## Phase 1 — Assignments (data, API, UI, filter)

### 1.1 New table `release_assignments`

Columns:
- `id` (pk)
- `release_id` (FK → releases.id, ON DELETE CASCADE)
- `user_id` (FK → users.id)
- `assigned_at` (datetime, default utcnow)
- `assigned_by` (FK → users.id, nullable — null if assignment was created by a system process)

Constraints:
- Unique `(release_id, user_id)`

New migration after M6.

### 1.2 API

- `GET /brain/releases/<job>/<release>/assignments`
  - Returns `[{user_id, first_name, last_name, username}]`
- `POST /brain/releases/<job>/<release>/assignments`
  - Body: `{user_ids: [int, ...]}`
  - Replaces the assignment set; returns the new list.
  - Writes a `ReleaseEvents` row with `action='update_assignments'` and payload `{added: [...], removed: [...]}` so the audit trail and History page see it.

### 1.3 Include `assignees` in the release payload

Add the array to `Releases.to_dict()` (or wherever `/brain/jobs/...` serializes). Job Log already loads the full payload; no extra round trip needed.

### 1.4 Assign UI

- Compact avatar pill cluster (initials) on the release row.
- Click opens a picker listing all `User`s where `is_active=True` with checkboxes.
- Cap visible avatars at 3 with `+N` overflow.
- Same picker available in `JobDetailsModal.jsx` if/when needed.

### 1.5 "Assigned to me" filter

- New state in `useJobsFilters.js`, persisted to `localStorage` as `jl_assigned_to_me`.
- Toggle button in the existing filter strip.
- Predicate: `release.assignees.some(a => a.user_id === currentUser.id)`.

---

## Phase 2 — Notifications

### 2.1 Extend `Notification` model

- Add nullable `job` (int) and `release` (string(16)) columns.
- Update `to_dict()` to include `job`, `release`, and a derived `release_label` (e.g. `"#1234-A — Acme Tower"`).
- Migration after the assignments migration.

### 2.2 New service `app/services/release_notification_service.py`

```
notify_assignees(release, event_type, payload, actor_user_id) -> int
```

- Iterates `release_assignments` for the release.
- Skips `actor_user_id` (no self-notifications).
- Creates one `Notification` per remaining assignee.

Message format per event type:

| Event | Message |
|---|---|
| `update_stage` | `#{job}-{release} stage changed: {from} → {to}` |
| `update_notes` | `#{job}-{release} notes updated` |
| `update_start_install` | `#{job}-{release} start install: {from} → {to}` |
| `update_fab_order` | `#{job}-{release} fab order: {from} → {to}` |
| `update_assignments` (assignment-itself) | `You've been assigned to #{job}-{release}` |

### 2.3 Hook in `JobEventService.create()`

After the event is committed, if `action ∈ {update_stage, update_notes, update_start_install, update_fab_order, update_assignments}`, call the notification service.

- `actor_user_id` from `get_current_user()` when in a request context; `None` for background syncs (Excel hourly, Trello webhook).
- For `update_assignments`, only notify newly-added users (not removed ones), and don't suppress the actor — they need to know who they assigned, but more importantly the assignee needs to know they're now on the hook.

### 2.4 Bell rendering

`NotificationBell.jsx` already polls and renders a list. Extend the dropdown to render release-typed notifications:
- Show `release_label` + the message body.
- Click → navigate to `/job-log?jumpTo={job}-{release}` (deep-link infra already exists).

---

## Anti-noise rules

- **Dedup window.** Within 5 minutes, collapse repeated identical `(event_type, release_id, user_id)` notifications into one — update the existing unread row instead of creating a new one. Prevents fat-finger spam.
- **Skip self.** Actor never gets a self-notification on `update_stage` / `notes` / `start_install` / `fab_order`.
- **System actors get through.** Excel hourly sync and Trello webhook changes still notify assignees. Surface the source in the message (e.g. `(via Excel)` or `(via Trello)`) so the recipient knows it wasn't a teammate.
- **Assignment notifications are not deduped** — being assigned is rare and important enough to ping every time.

---

## Decisions made (callable out for revisit)

- **Assignment itself sends a notification to newly-added assignees.** Default ON. Easy to flip if it turns out to be noise.
- **Avatar overflow cap is 3 + "+N".** Tunable.
- **Deactivated users keep their `release_assignments` rows.** They just stop receiving notifications (filter on `User.is_active`). No cleanup migration.

## Test plan

### Phase 1

- [ ] Add an assignee → row in `release_assignments`, also a `ReleaseEvents` audit row with `action='update_assignments'`.
- [ ] Remove an assignee → row deleted, audit row added.
- [ ] Pill cluster reflects current state; refresh-stable.
- [ ] Cap at 3 avatars + "+N" overflow.
- [ ] "Assigned to me" filter narrows correctly; persists across page reload.

### Phase 2

- [ ] Stage change on a release with two assignees (one is the actor) → only the non-actor gets a notification.
- [ ] Notes / start install / fab order changes each fire correctly with the right message.
- [ ] Three rapid stage changes within 5 min for the same release+assignee → one notification, not three.
- [ ] Click bell notification → lands on the right row in Job Log via `?jumpTo=`.
- [ ] Excel hourly sync triggers a stage change → assignees notified, message includes `(via Excel)`.
- [ ] Trello webhook triggers a stage change → assignees notified, message includes `(via Trello)`.
- [ ] Assigning Tiny → Tiny gets a single "you've been assigned" notification immediately.
- [ ] Deactivating a user mid-flight → no further notifications to them; existing unread notifications remain.

## Risks

- **Notification volume.** With four trigger actions, an active release could generate steady traffic. The 5-minute dedup is the main safety valve. Monitor the bell-noise feedback after rollout.
- **Background actors don't have a `user_id`.** Make sure `notify_assignees(actor_user_id=None)` notifies *everyone* on the release without a self-skip.
- **Assignment + immediate stage change.** If a user adds Tiny and then changes stage in the same UI flow, Tiny should get two notifications (one assignment, one stage change). That's correct — they're meaningfully different signals.

## Out of scope

- Email notifications.
- Trello card-member sync.
- Stage → role/team mapping ("automatic" next-guy resolution).
- Reassignment workflows (handing off ownership en masse).
