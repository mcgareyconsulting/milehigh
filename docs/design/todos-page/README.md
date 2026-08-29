# To-Do page cleanup — scoping notes (BUG-17)

**Status:** unblocked 2026-08-29. Scope decisions below are open; nothing here is built.
**Target:** `frontend/src/pages/ToDos.jsx` (411 lines), `frontend/src/services/todosApi.js`,
`app/brain/todos_routes.py`.

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

## Tier 1 — take now, no backend change

These are presentation-only and land entirely in `ToDos.jsx`.

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

**4. Page chrome patterns.** `board-column.tsx` (titled card with a count),
`empty-state.tsx`, `entity-view-tabs.tsx` (tabs carrying counts, preserving the owner
filter across a tab switch). Our status tabs (`STATUS_TABS`, `ToDos.jsx:23`) do not show
counts; the reference's do, and counts are what make a tab worth clicking.

**5. Owner initials on group headers.** Cheap, and we already compute `initials(u)`.

---

## Tier 2 — worth doing, needs a backend touch but no new table

**6. Group by owner as an alternative to due-urgency.** The clearest structural
difference: the reference groups into **owner cards** ordered by team speaking order;
we group into **due buckets** (`BUCKETS`, `ToDos.jsx:41`). Neither is wrong — owner
grouping answers *"what does each person owe?"*, due grouping answers *"what is on
fire?"*. **Recommendation: keep due-urgency as the default and add an owner-grouped
toggle**, rather than replacing it. We are a job shop, not a weekly leadership meeting;
"overdue" is the question people open this page with. Drop the speaking-order ordering
entirely — we have no speaking order — and fall back to alphabetical, which is what the
reference's README says to do anyway.

**7. Edit due date and owner from the row.** `PATCH /todos/<id>` currently takes
`status` only (`todos_routes.py:76`). Widening it to accept `due_date` and
`owner_user_id` is small and is the most likely real complaint about the current page —
a to-do's date is set once by the extractor and then only changeable in the meeting
review screen. **Keep the immutable `proposed_*` columns untouched** when doing this;
they are the audit record of what the agent inferred and must not be overwritten by a
human edit.

---

## Tier 3 — model changes, decide before building

**8. Create a to-do outside a meeting.** `ChecklistItem.meeting_id` is
`nullable=False`, so a standalone to-do is currently impossible by construction. Options:
make it nullable and accept that "checklist item" no longer means "from a meeting"; or
add a real `todos` table and make checklist items one *source* feeding it. The second is
the honest model and the more expensive one. **Do not decide this inside BUG-17** — it
is a product question, and BUG-17 was raised as a cleanup.

**9. Archive.** We have no archive; `status='done'` is terminal and the Done tab is our
"archive". If we ever add one, steal this contract verbatim from the reference's README,
because it is the non-obvious part:

> A to-do archives *because* it was completed. Restore therefore clears both
> `archived_at` **and** `completed_at`; clearing only `archived_at` would let the sweep
> re-archive it immediately.

That is a bug we would otherwise certainly ship.

**10. Rich-text descriptions.** `ChecklistItem.detail` is plain `db.Text` and the
extractor writes plain prose into it. The reference's `rich-text.ts` /
`rich-text-editor.tsx` are a self-contained markup stack. Adopting them is a scope
increase with no stated demand — **skip unless asked.**

**11. `visibility: private`.** Do **not** port this onto our role model. Ours is
enforced server-side (`todos_routes.py:42`, non-admins hard-scoped to their own rows) and
that invariant is load-bearing — it is stated in both the page and route headers. A
per-row `visibility` field layered on top of role scoping creates two overlapping
authorities on the same question. If per-row privacy is ever wanted, it should replace
the role scoping deliberately, not sit beside it.

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

## Suggested first slice

Tier 1 in one pass — three-tone urgency, expandable rows, muted completed state, counts
on the tabs. It is all frontend, it is the part a person actually feels, and it needs no
decisions from anyone. Tier 2 item 7 (edit due/owner) is the natural follow-up if the
cleanup is meant to reduce friction rather than just look better.

**Invariant that must survive any rewrite:** non-admins can only ever see or modify their
own items, and that is enforced server-side. Both `ToDos.jsx` and `todos_routes.py` state
it in their headers. Do not move scoping into the client.
