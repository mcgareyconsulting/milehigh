# Submittal ID Coherence Audit (Phase 1a)

**Scope:** `docs/feature-plan-2026-06-30.md` §1a. Answers the five audit
questions before §1b (due-date flow for all types) and §1c (split release) are
allowed to proceed.

**Method:** static read of `app/procore/procore.py`, `app/brain/drafting_work_load/`,
`app/brain/job_log/routes.py`, `app/trello/api.py`, `app/models.py`, plus the
prior production-data study in `docs/submittal-to-install-projection-findings.md`
(11-week live window, May 2026). No new prod queries were run for this pass —
the code-level picture below is consistent with, and explains, that data.

---

## tl;dr

`submittal_id` itself is stable and trustworthy — it's Procore's own id, used
directly as our unique key. The coherence problem is one level up: **a
logical scope of work (e.g. "Building #3 stair cores") passes through
DRR → GC → FC as three unrelated Procore records with three different
`submittal_id`s, and nothing in the code links them.** Every mechanism that
tries to bridge "the DRR I reserved a Rel number on" to "the release that
eventually lands in the Job Log" does so through a human typing the same
number twice, or through a fuzzy title match applied after the fact — never
through the id.

---

## 1. Is `submittal_id` stable across a submittal's open/close/type-change lifecycle?

**No — because there is no "lifecycle" at the id level.** `submittal_id` is
Procore's `resource_id`, stored verbatim as a string and used as the DB's
natural key (`Submittals.submittal_id`, `unique=True`) — see
`create_submittal_from_webhook` (`app/procore/procore.py:582-712`), which
looks up existence by `submittal_id` alone before creating a row.

Procore does not mutate an existing submittal's type in place. A phase
transition (DRR → GC → FC) closes the old submittal and Procore creates a
**new submittal record with a new id** for the next phase. This was confirmed
against live data in the earlier study: DRR/GC/FC are "three separate records
in Procore, not one record changing phase" (`docs/submittal-to-install-projection-findings.md:21-29`).
Consequently `submittal_id` is stable *within* a phase (it never changes for
a given row) but has **no continuity across phases** — there is no
`parent_submittal_id` or revision pointer anywhere in the payload we ingest.

## 2. Same description, different type — collapse or diverge?

**Diverge.** `create_submittal_from_webhook` only guards against duplicate
creation by `submittal_id`; there is no dedup or matching against
`title`/`project_number` anywhere in the ingestion path
(`app/procore/procore.py:598-601, 690-696`). Two submittals with identical
titles but different `type` become two independent `Submittals` rows.

The one place we *do* attempt title-based matching —
`get_submittals_by_project_id` (`app/procore/procore.py:406-419`, used to find
the FC drawing set for a release's deep-link button) — matches by normalized
title **within a single project, filtered to `type == "For Construction"`
only**. It doesn't reach back to a DRR/GC row and was never meant to; it's a
narrower, one-directional lookup. The prior study's attempt at a broader
DRR→GC→FC title match (project + title, no type filter) only lined up
**~9%** of scopes (`docs/submittal-to-install-projection-findings.md:57`) —
titles get reworded/typo'd between phases, so title matching is not a
reliable substitute for a real link.

`specification_section` is parsed from the Procore payload
(`app/procore/procore.py:362`) and logged into the diagnostic blob
(`parse_and_log_submittal_data`), but **is not persisted as a column** and is
not used anywhere for matching. It remains the most plausible candidate for a
real cross-phase key, flagged but unbuilt.

## 3. Does a type change mutate the id we key on?

**No, and it can't** — see §1. `check_and_update_submittal`
(`app/procore/procore.py:799-...`) is the only code path that updates an
existing row from a webhook, and it only ever touches `ball_in_court`,
`status`, `title`, and `submittal_manager`. `type` is written once, at
`create_submittal_from_webhook`, and never revisited. The invariant is
explicit in the file header: *"the update path needs no type handling"*
(`app/procore/procore.py` module docstring). So the row we key on is
immutable once created; the risk isn't mutation, it's that a "type change" in
Procore's world is actually a brand-new row we have no way to associate with
the old one.

## 4. Source of truth: Procore id vs. our row id; known divergence

- **Source of truth for identity:** `submittal_id` = Procore's raw id,
  stored as `String(255)`, unique. Our own `id` (integer PK) is a pure
  internal surrogate never exposed to Procore or used for matching — it's
  SQLAlchemy bookkeeping only.
- **`Submittals.rel`** (101–998, job-agnostic, `app/procore/procore.py:52-56`)
  is a *reservation* made on a DRR row via the manual popup
  (`assign_rel_manual`, `app/procore/procore.py:170-199`; endpoint
  `app/brain/drafting_work_load/routes.py:652-698`). It lives **only on that
  one DRR `Submittals` row.**
- **`Releases.release`** (the actual Job Log release number) is typed by a
  human into Excel/Trello, ingested via `create_job_record_from_excel_data`
  (`app/trello/api.py:454-480`: `release_number =
  str(excel_data.get("Release #", ""))`) or pasted as CSV into
  `/job-log/release` (`app/brain/job_log/routes.py:1869-...`, expects a
  literal `Release #` column value). **Neither path reads `Submittals.rel` or
  `submittal_id` at all.** The connection between "the number reserved on the
  DRR" and "the number that shows up in the Job Log" is **100% human
  convention** — a drafter/PM is trusted to type the same number into
  Excel/Trello that was reserved on the DRR. Nothing in code enforces,
  suggests, or verifies that they match.
- A **second, independent** link exists: `Releases.procore_submittal_id`,
  captured "at FC-drawing lookup time" via the title-matched
  `get_submittals_by_project_id` call (`app/brain/job_log/routes.py:343-349`)
  — this points at the **FC-phase submittal**, found by fuzzy title match
  *after* the release already exists. It has no relationship to the DRR's
  `submittal_id` or to `Submittals.rel` either.
- **No reconciliation/health check exists today** that cross-checks a
  DRR's reserved `rel` against the eventual `Releases.release` value, or
  flags a DRR that closed (transitioned to GC/FC) while still holding an
  unconsumed `rel`. `_globally_taken_rel_numbers`
  (`app/procore/procore.py:80-125`) explicitly *stops* treating a Closed
  DRR's `rel` as taken, on the documented assumption that "a Closed DRR is on
  its way to being an active release that (a) catches" — i.e. the code
  assumes the human-typed `Releases.release` will show up and reserve the
  number through the *other* mechanism. If that number is retyped
  incorrectly, or the human types a different number, **there's no error,
  alert, or trace** — the DRR's reservation simply evaporates once its status
  leaves the "not Closed" filter.
- **Event-log-vs-row divergence** (`SubmittalEvents` vs. `Submittals`): a
  known, separate issue, already audited and intentionally deferred — see
  prior findings (rapid ball-in-court flip within the 60s reconcile window
  can drop an event while the row still updates correctly; row is always the
  source of truth). Not re-litigated here since it doesn't bear on
  cross-phase id coherence, only on audit-trail completeness.

## 5. Findings summary (for §1b / §1c / §2)

1. **`submittal_id` is not the join key that carries a scope of work from
   DRR through to a Job Log release — it can't be, since Procore issues a new
   id per phase.** Any future design must join on something else:
   `Submittals.rel` (job-agnostic reservation) or a to-be-added Procore field
   like `specification_section` (parsed but not persisted or used).
2. **Today, `Submittals.rel` ↔ `Releases.release` is a purely procedural
   match** (human types the same number twice), with **no code-level
   validation, transfer, or alerting** if it's typed wrong or the DRR closes
   without ever producing a matching release. This is the real "coherence"
   risk the plan was worried about — not id mutation, but a silent,
   unverified hand-off.
3. **§1b (due-date/start-install for all types) already has a complete,
   reviewed design** — `docs/start-install-all-submittals-plan.md` (status:
   ON HOLD, pending client confirmation) — and it independently reaches the
   same conclusion: `rel` is "the sole join key," assignment stays DRR-only,
   and a date on a non-DRR (GC/FC) submittal cannot propagate because there's
   no link back to whichever DRR the scope originated from. That plan's
   "deferred handoff" design (store the date regardless of type; only wire it
   into `PendingStartInstall` once/if a Rel exists) is consistent with this
   audit and does not require solving cross-phase linkage to ship — it
   sidesteps the gap rather than closing it. Verified still accurate against
   current code (the `drr_rel_required` gate is still live in
   `tests/dwl/test_start_install.py`).
4. **§1c (split a release)** — "auto-assign next-available release numbers on
   split, reuse §2 auto-pull logic" — should reuse `next_rel_number`
   (`app/procore/procore.py:129-165`), the same DRR-reservation sequence, not
   invent a second numbering scheme. Note `next_rel_number`/`assign_rel_manual`
   only operate on `Submittals` (DRR) rows today; a split happening at the
   Job Log level (on an existing `Releases` row, post-FC) has no existing
   submittal to attach a reservation to, so it's a new call site, not a
   reused one as-is.
5. **§2 ("+ Verbal Release" auto-pull)** describes wanting "the same
   mechanism the DWL uses now" — worth flagging that the DWL's mechanism
   (`next_rel_number`) and the Job Log's current release-creation paths
   (`create_job_record_from_excel_data`, `/job-log/release`) are **not
   currently wired together** — the Job Log still expects a human-typed
   `Release #`. Wiring `next_rel_number` into either Job Log creation path
   would be new integration work, not a reuse of an existing connection.

## Open question carried forward

If MHMW wants real cross-phase coherence (not just the procedural-match
status quo), the fix is upstream in Procore, per the prior study's
recommendation: find or add a linking field (`specification_section` is the
best current candidate — already fetched, not persisted) and persist it on
`Submittals`, then key `rel` continuity off that instead of `submittal_id`.
That's a design decision for whoever picks up the "change how assignment
works" half of §1, not something this audit resolves.
