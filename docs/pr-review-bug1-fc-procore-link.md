# PR review — BUG-1: FC / Procore link graying on the Job Log

**Roadmap ID:** Workstream 3 · **BUG-1**  
**Branch intent:** Fix missing / stuck-empty `Releases.viewer_url` so Job Log Procore / FC drawing links stop appearing gray after collection misses and FC set updates.  
**Primary source complaint:** Colton / Bill 2026-08-06 working session [L1334–1371] — *“the Procore one is always gray… connecting to the FC set… if there's an update in the FC set… number versus name is different.”*  
**Reviewer handoff:** This doc is written for a second-pass model review (Claude). Prefer challenging the design, edge cases, and failure modes over restating the diff.

---

## 1. Executive summary

| | |
|---|---|
| **User-visible symptom** | Job Log release number is plain (gray) text instead of a blue Procore/drawing link; in the drawing hub, **View in Procore** is disabled gray with “No FC link found.” |
| **True condition** | `Releases.viewer_url` is `NULL` or `""`. The UI does not invent a link. |
| **Not a CSS bug** | Blue vs gray is gated on truthy `viewerUrl` / `row.viewer_url` in `ReleaseNumberLink`, `JobsTableRow` Release # cell, and `PdfVersionHistoryModal`. |
| **Number vs name** | **Intentional product split**, not fixed here: **Job name** opens the detail/cockpit modal; **Release #** opens drawing hub or Procore when a URL exists. Combining those is a separate UX track (modal merge). |
| **Fix surface** | Backend collection only: `app/procore/procore.py` (fetch + Final PDF resolution) and `app/procore/fc_retry_worker.py` (who gets retried + how we persist). |
| **No migration** | Schema unchanged. Safe to deploy without DDL. |

---

## 2. How the link is supposed to work (baseline)

```
Release created (paste / verbal / Trello path)
    → first-attempt Procore lookup (card creation / add_procore_link_to_trello_card)
    → Releases.viewer_url (+ optional procore_submittal_id)
    → Trello “FC Drawing” attachment when card_id present

If first attempt misses (Final PDF Pack not ready yet, ~up to 24h):
    → nightly fc_retry_worker.retry_missing_fc_viewer_urls(trigger="cron")
    → admin manual trigger also available
    → FcCollectionRun row records succeeded / still_missing / errored

Job Log UI reads viewer_url on each release row:
    → present → blue link / hub “View in Procore”
    → absent  → gray plain text / disabled Procore chip
```

**Collection pipeline (shared by first attempt + retry):**

1. Resolve Procore **project** from job number (`project_number` map).
2. List project **submittals**, keep **For Construction** whose title matches `{job}-{release}` (`_identifier_matches` word-boundary).
3. On matching submittal(s), find **Final PDF Pack** in `last_distributed_submittal.distributed_responses`.
4. Load **workflow_data** attachments; match `approver_id` → `viewer_url`.
5. Persist absolute `https://app.procore.com…` URL on the Releases row.

---

## 3. Root-cause analysis (why it went gray “a lot”)

Ordered by leverage. Several of these compound: a miss at (A) never reaches (B); a miss at (B) looks identical in the UI to “FC not ready yet.”

### A. Unpaginated submittal list (high confidence)

**Before:** `fetch_all_submittals` / `get_submittals_by_project_id` did a **single** GET to  
`/rest/v1.1/projects/{id}/submittals` with no `page` / `per_page` loop.

**Effect:** On projects with more submittals than the first page, FC rows that live later in the list never enter `submittals_for_release` → permanent “no matching For Construction submittal” → gray forever, including after a healthy FC set exists in Procore.

**Note:** `ProcoreAPI.get_submittals` already paginated (v2). The FC viewer path did not use it.

### B. Thin list payload after FC set updates (high confidence — matches transcript)

**Before:** `get_final_pdf_viewers` only read `last_distributed_submittal` **from the list object** and bailed if `distributed_responses` had no exact `"Final PDF Pack"`.

**Effect:** List endpoints often omit or stale nested distribution after re-distribute / FC set update. Colton’s “I updated the FC and I know it is connected” still yields gray in Brain because we never detail-fetched the submittal or re-read workflow attachments.

### C. Exact response name only (medium)

**Before:** `response_name == "Final PDF Pack"` only.

**Effect:** Renamed / variant labels after an update (e.g. “Final PDF Pack - Revised”) skipped the pack even when present.

### D. Retry candidate filter too narrow (high)

| Filter (old) | Problem |
|---|---|
| `viewer_url.is_(None)` only | Empty string `""` never retried; UI treats `""` as gray. |
| `is_active.is_(True)` only | Legacy rows with `is_active IS NULL` excluded; elsewhere “active” means True **or** NULL (`active_releases_filter`). |
| `released >= today-7` only | After day 7, still-missing rows abandoned. FC lag + late pack + updates can exceed a week. |
| No path for `released IS NULL` | Rows without a released date never entered the queue. |

### E. Persist by `(job, release)` only (latent / forward-compat)

**Before:** `_persist_viewer_url` used `filter_by(job=…, release=…).first()`.

**Effect:** With job-number wrap + uniqueness now including project name (BUG-3), two active/archived rows can share digits. Retry could write the URL onto the wrong row. Persist now prefers **primary key**.

### F. Out of scope for this PR (called out for honesty)

| Observation | Why not “fixed” here |
|---|---|
| Number vs name different click targets | Product split; merging is N7 / modal work. |
| Stale **non-empty** viewer_url after FC revises PDF | Retry only targets **missing** URLs. Refreshing a live URL when Procore revises is a separate “re-collect” feature. |
| First-page-only `fetch_all_projects` | Project map is still a single projects GET; if that list is truncated for huge companies, job→project resolution fails (“no Procore project for job”). Not observed as the main complaint; same pattern as pre-fix. |
| Procore rate limits / token errors | Already bucketed as `errored` in `FcCollectionRun`; no new backoff redesign. |

---

## 4. What changed (file-level)

### `app/procore/procore.py`

| Change | Why |
|---|---|
| `_submittal_type_name` / `_is_for_construction` | Tolerate type as dict or string; minor naming drift. |
| **Paginated** `fetch_all_submittals` (`page` + `per_page=100`, hard page cap 200) | Fix (A). Fallback to `ProcoreAPI.get_submittals` if first response is not a list. |
| `get_submittals_by_project_id` → filter over paginated full list | Same as first-attempt path. |
| `_final_pdf_approver_ids` | Casefold + tolerant “final”+“pdf” name match. |
| `_normalize_viewer_url` | Absolute vs relative path; empty → None. |
| **`get_final_pdf_viewers` hardened** | (1) list distribution, (2) **detail refetch** if no pack ids, (3) workflow match by approver_id, (4) **workflow PDF fallback** if distribution metadata still empty. |

### `app/procore/fc_retry_worker.py`

| Change | Why |
|---|---|
| `LOOKBACK_DAYS = 30` (was 7) | (D) longer recovery window. |
| Missing URL = `NULL` **or** `""` | (D) empty string. |
| `active_releases_filter()` | (D) align with rest of app. |
| Recent if `released` in window **or** (`released` null and `last_updated_at` recent) | (D) no-released-date rows. |
| Candidate tuple includes **`release.id`** | (E) correct persist under job# wrap. |
| `_persist_viewer_url(release_id, …)` prefers `query.get(id)` | (E). |

### Tests

`tests/procore/test_fc_viewer_url.py` (new) — pure unit tests, no live Procore:

- Type matching (dict / string)
- Viewer URL normalization
- Approver id extraction (exact + tolerant)
- Final PDF path with list payload
- **Detail refetch** when list lacks distribution
- Workflow **fallback** when approver ids do not match attachments
- `submittals_for_release` filter

### Docs

`docs/roadmap.md` — BUG-1 marked fixed with one-line summary.

---

## 5. Behavioral contracts (what must stay true)

1. **Never invent a URL** in the UI. Gray remains correct when Procore has no matchable pack.
2. **Do not clear** an existing non-empty `viewer_url` on retry failure — worker only writes on success.
3. **Identifier match** stays word-boundary (`_identifier_matches`) — no return to substring false positives (`410-108` inside `1410-1087`).
4. **For Construction only** — DRR / GC Approval must not drive FC viewer_url.
5. **Trello link add** remains best-effort after DB persist (failure logs warning; URL still saved).
6. **FcCollectionRun** still records one run summary + details buckets; prune last 30 runs.

---

## 6. Risks & review focus areas

### R1 — Workflow fallback quality (important)

If distribution metadata is gone but workflow has multiple PDFs, fallback scores:

1. name contains `"final"`
2. else PDF-ish name
3. else any attachment with `viewer_url`

**Risk:** Wrong attachment linked (e.g. cover sheet instead of full set).  
**Mitigation:** Prefer “final” in name; only used after approver-id path fails; log `final_pdf_viewer_fallback`.  
**Review ask:** Is fallback acceptable for Colton’s “connected in Procore but gray in Brain,” or should we refuse fallback and only detail-refetch?

### R2 — More Procore API calls

Detail GET + workflow GET per unmatched list item increases load during nightly retry and first-attempt paths that call `get_final_pdf_viewers`.

**Mitigation:** Detail only when list has no Final PDF approver ids; 0.5s sleep between releases in worker (unchanged); pagination adds pages only for large projects (necessary).  
**Review ask:** Cap detail refetches per project? Cache workflow by submittal_id within a run? (Not implemented.)

### R3 — Page cap 200 × 100

Hard stop after 200 pages. Pathological projects beyond 20k submittals would still truncate. Unlikely for MHMW; log `fetch_all_submittals_page_cap`.

### R4 — Type name `startswith("for construction")`

Slightly broad. Unlikely Procore types; review if too loose.

### R5 — `LOOKBACK_DAYS = 30` volume

More candidates per night → more Procore traffic. Prefer correctness over thrift given Colton’s complaint.  
**Review ask:** 14 vs 30?

### R6 — No automated integration test against live Procore

Unit tests mock workflow/detail. Sandbox/prod validation still needs a manual or scripted pass against a known gray release (e.g. Columbine-class FC).

### R7 — Stale non-empty URL after FC revise

Out of scope (see §3.F). If users report “link works but wrong revision,” that is a **refresh** feature, not this PR.

---

## 7. Deploy & ops

| Step | Notes |
|---|---|
| Migration | **None** for BUG-1. |
| Deploy order | App-only; no dependency on BUG-3 uniqueness migration. |
| After deploy | Nightly cron picks up, **or** admin manual FC retry (`retry_missing_fc_viewer_urls(trigger="manual")`). |
| Observe | `FcCollectionRun` latest row: `candidates`, `succeeded`, `still_missing`, `errored`; logs `final_pdf_viewer_fallback`, `fetch_all_submittals_page_cap`. |
| Smoke | Pick a release that is gray with a known FC pack in Procore → run manual retry → confirm `viewer_url` set and Release # blue / hub Procore enabled. |

**Related (this branch, not this review doc’s subject):** BUG-2 order 0→null; BUG-3 uniqueness `(job, release, job_name)` + migration `releases_unique_job_release_name.py`. Review those separately if the PR ships the full workstream pile.

---

## 8. Suggested test commands

```bash
# Unit coverage for this fix
pytest tests/procore/test_fc_viewer_url.py -q

# Optional: broader procore suite if time
pytest tests/procore/ -q
```

Manual / sandbox:

1. Identify active release with empty `viewer_url` and a For Construction submittal titled `{job}-{release}…` that has Final PDF Pack in Procore.
2. Trigger admin FC retry (or wait for cron).
3. Confirm row updates; Job Log Release # blue; hub “View in Procore” live.
4. Optional: release on a high-submittal project that previously always missed (pagination).

---

## 9. Reviewer checklist (Claude)

Please specifically answer:

1. **Is the workflow PDF fallback (R1) an acceptable tradeoff**, or should success require an explicit Final PDF Pack / approver_id match only?
2. Are there **other writers** of `viewer_url` that still use unpaginated or non-detail paths and would leave a dual code path? (Grep: `get_final_pdf_viewers`, `get_viewer_url_for_job`, `fetch_all_submittals`, `add_procore_link_to_trello_card`.)
3. Does **`_persist_viewer_url` by id** fully address multi-row same job-release under BUG-3, or can `card_id` / Trello still attach to the wrong card?
4. Any **security / open-redirect** concern on normalizing relative `viewer_url` to `app.procore.com`? (We only prefix our known host when path-relative.)
5. Should **retry also re-collect** when `viewer_url` is non-empty but older than last Procore distribution? (Scope expansion — recommend yes/no.)
6. Confirm **no regression** to identifier matching tightness and For Construction gating.
7. Flag any **logging-standard** issues on new log events (`final_pdf_viewer_fallback`, etc.) if the project standard requires structured kwargs only (this code largely uses structured kwargs).

---

## 10. Diff anchors (for navigation)

| Area | Location |
|---|---|
| Pagination + type helpers | `app/procore/procore.py` — `fetch_all_submittals`, `_is_for_construction` |
| Final PDF resolution | `app/procore/procore.py` — `get_final_pdf_viewers`, `_final_pdf_approver_ids`, `_viewer_results_from_workflow*` |
| Retry candidates + persist | `app/procore/fc_retry_worker.py` — `_candidate_snapshot`, `_persist_viewer_url`, `LOOKBACK_DAYS` |
| UI gray condition (unchanged) | `frontend/src/components/ReleaseNumberLink.jsx`, `JobsTableRow.jsx` (Release #), `PdfVersionHistoryModal.jsx` (“View in Procore”) |
| Cron entry | `app/__init__.py` — schedules `retry_missing_fc_viewer_urls` |
| Tests | `tests/procore/test_fc_viewer_url.py` |

---

## 11. One-paragraph PR description (copy-paste)

> Fix Job Log FC/Procore link graying (BUG-1). Gray meant `viewer_url` was missing, not a frontend bug. Collection now paginates Procore submittal lists (large projects were truncated), re-fetches submittal detail when list payloads lack Final PDF Pack after FC set updates, tolerates Final PDF naming drift, and falls back to workflow PDF viewer URLs when distribution metadata is empty. The nightly retry worker treats empty-string URLs as missing, uses the standard active-release filter, extends lookback to 30 days, and persists by release primary key. Number-vs-name click difference is intentional and unchanged. Unit tests cover resolution paths without live Procore.

---

## 12. Second-pass review findings (Claude, 2026-08-06)

Findings confirmed against the code on `claude/procorel-ink-bug-review-rw52et`
(commit `50d207e`). Every factual claim in §§2–6 checked out: the UI gray
condition is gated on truthy `viewer_url` exactly where §10 says
(`ReleaseNumberLink.jsx:37`, `JobsTableRow.jsx:1372`,
`PdfVersionHistoryModal.jsx:330`); the candidate-filter widening matches
`active_releases_filter` semantics and the `Releases` column types
(`released` is `Date`, `last_updated_at` is `DateTime`); the cron entry,
pagination, detail refetch, and PK-first persist are all as described.
`pytest tests/procore/` and the full suite pass.

**Checklist answers (§9):**

1. **Fallback (R1): keep, with two tightenings applied in this review.**
   (a) The detail refetch now also runs when the *list* payload has approver
   ids that fail to match workflow attachments — previously stale ids after a
   re-distribute skipped detail entirely and jumped straight to the name-based
   fallback. (b) The fallback no longer accepts arbitrary attachments: only
   `final`-named or PDF-ish names qualify; photos/markups are refused (a wrong
   link is worse than a gray one). `workflow_data` is now fetched once per
   submittal instead of up to twice.
2. **Dual code path: yes — fixed.** `backfill_fc_drawing_viewer_urls.py`
   redefined an *unpaginated* `fetch_all_submittals` plus a strict
   `submittals_for_release` that raised `AttributeError` on string/None `type`
   payloads. It now imports the shared paginated/tolerant versions from
   `app.procore.procore`. No other writers of `viewer_url` exist
   (`card_creation.py` and `/procore/add-link` both go through the shared
   hardened path).
3. **Persist by id: yes for the worker.** The first-attempt path
   (`add_procore_link_to_trello_card`) still resolves by `(job, release)`
   `.first()`, but it runs at creation time when a wrapped duplicate cannot
   yet exist for that identifier, so left as-is; flag if a paste-time
   collision is ever observed.
4. **No open-redirect concern.** `viewer_url` values come from Procore API
   responses, not user input; only path-relative values are prefixed, and a
   protocol-relative `//host` value would still resolve under
   `https://app.procore.com//…`.
5. **Re-collect non-empty URLs: defer.** Agree with §3.F — a refresh feature
   with its own staleness signal (compare `last_distributed_submittal`
   timestamps), not a retry-worker tweak.
6. **No regression** to identifier tightness (word-boundary
   `_identifier_matches` unchanged, covered by tests) or FC gating
   (`_is_for_construction` excludes DRR/GC Approval; `startswith` breadth is
   acceptable — no colliding Procore type names in use).
7. **Logging: procore.py events comply; the worker's did not.** Sentence-style
   event names (`"FC retry worker starting"`, `"FC retry: persist failed"`, …)
   pre-dated this PR but the ratchet applies to touched files — renamed to
   structured events (`fc_retry_started`, `fc_retry_persist_failed`,
   `fc_retry_finished`, …). Ops note: grep for `fc_retry_` after deploy, not
   "FC retry". Also added the missing `fetch_all_submittals_page_error`
   warning when pagination dies mid-stream — a silently truncated list
   otherwise reads as "no matching FC submittal" (still_missing) instead of
   an error.

**Risk asks:** R5 — keep 30 days (correctness over thrift, per doc). R2 —
the single workflow fetch per submittal (above) removes the double-fetch;
per-project detail caps not needed at MHMW volumes.

New tests: stale-list-approver-ids resolved via detail refetch; fallback
refuses non-PDF attachments. 15 FC viewer tests total, all passing.

---

*Written for PR ship with Workstream 3 bug pile. Elevate to Claude with this file + the procore/fc_retry diffs as the review package.*
