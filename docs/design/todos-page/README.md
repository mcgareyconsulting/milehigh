# To-Do page cleanup — scoping notes (BUG-17)

**Status:** unblocked 2026-08-29, scope narrowed the same day. Nothing here is built.
**Scope: frontend / quality-of-life only — no backend behavior changes** (Daniel,
2026-08-29). Everything that would alter the API, the model, or what the server enforces
is listed under *Out of scope* and must not be picked up as part of BUG-17.
**Target:** `frontend/src/pages/ToDos.jsx` (411 lines) — and `todos_routes.py` /
`todosApi.js` for reading only, not changing.

**Reference material:** the HPB EOS app's standalone To-Dos page, delivered by Daniel
2026-08-29 as `eos-todos-reference.zip` (44 files, ~6,850 lines). It lives at
`~/Desktop/Reference/eos-todos-reference/` and is **deliberately not in this repo** —
same convention as the meeting transcripts, and this repo is public while that is another
app's source. Its own `README.md` is the authoritative tour of the bundle; this file only
says what crosses over to us.

---

## Read this first: we do not have a to-do table

This is the fact that reframes the whole task, and it is easy to miss because both apps
call the thing a "to-do".

| | Reference | Us |
|---|---|---|
| Storage | standalone `todos` Firestore collection | `ChecklistItem` rows (`app/models.py`, table `checklist_items`) |
| Origin | created by a person, any time | **only** by the meeting extractor, from a transcript |
| Identity | a to-do is a first-class record | a to-do is *a checklist item that got accepted and has an owner* |
| Done | `completed_at` timestamp | `status` enum: `proposed` → `accepted` → `done` (+ `rejected`) |
| Archive | `archived_at` timestamp + Monday sweep | **does not exist** |
| Create from the page | yes (`AddTodoModal`) | **no** — there is no create path at all |
| Delete from the page | yes | **no** |
| Edit title/description/due/owner | yes (`EditTodoDrawer`) | **no** — `PATCH /todos/<id>` accepts `status` only |
| Scoping | `visibility: "team" \| "private"` field, compared to `uid` | role-based: admin sees all, non-admin hard-scoped to `owner_user_id == self` |

`ChecklistItem` also carries a lot the reference has no concept of: `item_type`
(action / needs_gc_update / decision / risk / fyi), `gc_facing`, the immutable
`proposed_owner_user_id` / `proposed_due_date` / `confidence` inference record,
`release_id` / `submittal_id` links, `expected_update` + `brain_update_pending`
(the BB-meeting drift signal), and the `matched_job_*` owner-inference fields.

**So "port the reference page" is not a coherent instruction.** Its entire write model
(`actions.ts`: `addTodo`, `deleteTodo`, `setTodoArchived`, `updateTodoMeta`, …) has no
counterpart here, and giving it one is a model change, not a cleanup. The three tiers
below separate what is free from what is a decision.

---

## In scope — all frontend, all in `ToDos.jsx`

Seven items. None changes the API, the model, or server-enforced behavior — item 4
changes how the page *fetches*, which is still frontend, but read its tradeoff.

**1. Three-tone due urgency.** `lib/due.ts` (`dueToneClass`) uses overdue → red,
within 14 days → amber, otherwise → muted, and *completed items never shout*. We
currently only distinguish overdue and due-today (`ToDos.jsx:193`, `:350-351`). The
14-day amber band is the useful addition, and the "done is never colored" rule is a real
bug class we should adopt explicitly.

**2. View-first row anatomy.** `todo-list-row.tsx` — click the **title** to expand the
description inline; the checkbox and edit affordance are separate click targets that
`stopPropagation`. Ours has no expand, so `detail` is either always shown or not shown.
This is the single biggest readability win in the bundle.

**3. The `closedPending` state.** A to-do completed but not yet archived renders in a
muted row rather than struck through — *"no strikethrough, stays readable"*. Ours flips
to `done` terminally, so our equivalent is the gap between "marked done" and "filtered
out by the Open tab". Worth mirroring the muted treatment.

**4. Counts on the status tabs — the one item with a tradeoff.** `entity-view-tabs.tsx`
carries a count per tab and preserves the owner filter across a tab switch. Ours
(`STATUS_TABS`, `ToDos.jsx:23`) show no counts, and counts are what make a tab worth
clicking.

**This one is not free, though it is still frontend-only.** The page fetches per tab —
`fetchTodos({ status, owner })` at `ToDos.jsx:119`, refetching whenever `status` changes
(`:123`) — so it only ever holds the current tab's rows and cannot count the others. The
fix is to fetch `status='all'` once (the route already supports it,
`todos_routes.py:51`) and move the status split client-side, which the page is already
shaped for: `item_type`, job and text all filter client-side today.

The cost: for an admin that pulls every accepted **and** done to-do in one response
instead of one tab's worth. Check the real row count against production before
committing to it — if it is large, drop this item rather than paginate, since the rest of
the list delivers most of the value. **If the owner filter also moves clientward as part
of this, scoping must not follow it** — see the closing invariant.

**5. Page chrome.** `board-column.tsx` (titled card with a count) and `empty-state.tsx`.
Our empty state is a bare sentence (`ToDos.jsx:320`).

**6. Owner initials on group headers.** Cheap, and we already compute `initials(u)`.

---

**7. Group by owner, as a toggle.** The clearest structural difference: the reference
groups into **owner cards**; we group into **due buckets** (`BUCKETS`, `ToDos.jsx:41`).
Neither is wrong — owner grouping answers *"what does each person owe?"*, due grouping
answers *"what is on fire?"*.

**Verified frontend-only:** `to_dict` already returns `owner_user_id` **and**
`owner_name` (`app/models.py:1693-1694`), so grouping by owner is a client-side regroup
of data the page already holds. No API change.

**Keep due-urgency as the default and add owner as a toggle**, rather than replacing it.
We are a job shop, not a weekly leadership meeting; "overdue" is the question people open
this page with. Drop the reference's speaking-order ordering — we have no speaking order —
and fall back to alphabetical with "Unassigned" last, which is what its own README says to
do in that case.

---

## Out of scope for BUG-17

Not because they are bad, but because they change backend behavior and this pass does
not. Each stays recorded so the next person does not have to re-derive it.

**Editing a to-do's due date or owner from the row.** `PATCH /todos/<id>` accepts
`status` only (`todos_routes.py:76`). Widening it is small and is probably the most
*useful* thing on this list — a to-do's date is set once by the extractor and is then
only changeable in the meeting review screen. It is still an API change. When it is
taken: **leave the `proposed_*` columns alone**; they are the immutable record of what
the agent inferred and must not be overwritten by a human edit.

**Creating a to-do outside a meeting.** `ChecklistItem.meeting_id` is `nullable=False`,
so a standalone to-do is impossible by construction. Either make it nullable and accept
that "checklist item" stops meaning "from a meeting", or add a real `todos` table and
make checklist items one *source* feeding it. The second is the honest model and the
more expensive one. A product question, not a cleanup.

**Archive.** We have no archive; `status='done'` is terminal and the Done tab is our
version. If one is ever built, steal this contract verbatim from the reference — it is
the non-obvious part:

> A to-do archives *because* it was completed. Restore therefore clears both
> `archived_at` **and** `completed_at`; clearing only `archived_at` would let the sweep
> re-archive it immediately.

That is a bug we would otherwise certainly ship.

**Rich-text descriptions.** `ChecklistItem.detail` is plain `db.Text` and the extractor
writes plain prose into it. The reference's `rich-text.ts` / `rich-text-editor.tsx` are a
self-contained markup stack. Scope increase, no stated demand.

**Per-row `visibility: private`.** Do **not** layer this onto our role model. Ours is
enforced server-side (`todos_routes.py:42`, non-admins hard-scoped to their own rows) and
that invariant is load-bearing — stated in both the page and route headers. A per-row
visibility field on top of role scoping creates two overlapping authorities on the same
question. If per-row privacy is ever wanted it should *replace* role scoping deliberately,
not sit beside it.

---

## Drop entirely

Everything below is in the bundle and has no path into this codebase:

- **All Firestore** — `lib/firebase/*`, `_infra/firestore.rules.todos.snippet`,
  `_infra/firestore.indexes.json`. We are Flask + Postgres with session auth.
- **Next.js server actions / RSC** — `actions.ts`, `page.tsx`'s server-component read
  model. We are a Vite SPA calling a REST API; the read model belongs in `ToDos.jsx` +
  `todos_routes.py`.
- **Google Tasks two-way sync** — `lib/google/*`, `sync-google-tasks-button.tsx`,
  `app/(app)/settings/actions.ts`. Out of scope, no demand.
- **Rocks / milestones** — `milestone-todo-row.tsx`, `lib/milestone-visibility.ts`, and
  the second column they populate. We have no rocks. *Note for later:* **D8 (EOS Module)
  is on the roadmap** and if it lands with rocks, this column and its 14-day
  reminder-not-inventory rule become directly relevant. Do not build it now; do not
  delete this paragraph.
- **Speaking order** — `lib/l10/speaking-order.ts`. No counterpart.
- **`lib/csv-import.ts`** — 507 lines carried for one function (`normalizeDescription`,
  which repairs line breaks in Ninety exports). We have no Ninety import.
- **Firebase scheduled functions** — `functions/src/archive-stale-todos.ts`. Only
  relevant if item 9 is ever taken, and then as a design reference for the sweep, not
  as code.

---

## Suggested order

Items 1-3, 5 and 6 first — urgency tones, expandable rows, the muted completed state,
the column/empty-state chrome, owner initials. They are independent of each other, need
no refetch change, and are the part a person actually feels.

Then item 7 (owner toggle), which is the largest single change but still a pure regroup.
Take item 4 (tab counts) last, or not at all — it is the only one that changes how the
page loads, and it is the only one worth dropping if the row count says so.

**Invariant that must survive any rewrite:** non-admins can only ever see or modify their
own items, and that is enforced **server-side**. Both `ToDos.jsx` and `todos_routes.py`
state it in their headers. Do not move scoping into the client — and note that item 4's
refetch change moves *filtering* clientward, which is fine, while scoping must not follow
it.
