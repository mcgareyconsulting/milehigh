# Logging work — resume notes (2026-07-05)

Personal catch-up doc. Untracked, in the main working tree (not part of any PR).
Delete when you don't need it anymore.

## Where things stand

**Everything from today is committed, pushed, and in a PR. Nothing is at risk.**

- **PR #280** — https://github.com/mcgareyconsulting/milehigh/pull/280
  Branch `chore/logging-cleanup`, 10 commits, 38 files, ~570 log call sites.
  Up to date with `main` (PR #279 merged in cleanly). Ready to review + merge.
- Worktree lives at `../worktree/chore/logging-cleanup` (sibling of this repo).
- Test suite is at its normal baseline: **807 passing, 8 pre-existing failures**
  (those 8 fail on `main` too — environmental, unrelated to logging).

## What we did today (the short version)

Started from the Render log spam complaint, ended up rebuilding the logging foundation:

1. **Security:** closed a DB-credential leak (startup log) and a Trello API key/token
   leak (card-update payload prints). Both were going to stdout.
2. **Noise:** activated the dead gunicorn access-log filter, silenced empty poll logs.
   This was the bulk of daily volume at 30 users.
3. **Uniformity:** one logger idiom, structured events instead of `print()`/f-strings,
   single-rendered JSON, a canonical field registry. ~570 call sites.
4. **Reliability:** restored stack traces in `except` blocks that were swallowing them
   (incl. two silent Procore failures). Kept permanent outbox failures at ERROR.
5. **Docs:** wrote the standard + guide (see below), updated CLAUDE.md so future work
   complies by default.
6. Found + fixed two incidental bugs (a shadowed loop var in DWL bump logging; CLAUDE.md
   describing dead `SyncContext` as active).

## Reference docs (all on the branch, in `docs/`)

- `docs/logging-standard.md` — the enforceable spec (idiom, events, registry, levels,
  durability rule). **This is the one to skim first tomorrow.**
- `docs/observability-guide.md` — the wider landscape, the "logs vs events vs metrics"
  explainer, the maturity ladder, and the annotated reading list.
- `docs/logging-cleanup-plan.md` — the original cleanup plan.

## Next step (decided, outlined, NOT started)

The standard defines two targets we haven't built yet: **§7 correlation** (a `request_id`
threaded through every log line, including across the async/threadpool/scheduler
boundaries) and **§5 the wide completion line** (one fat structured event per
request/webhook/job). These are one piece of work — correlation is the foundation, the
wide line rides on it.

**Status:** fully outlined in the chat transcript. It's **not critical** and it's
**heavier than the cleanup** (it touches live request/response hooks + the threadpool +
scheduler entry points — real plumbing, not find-and-replace). We agreed to do it fresh,
not tired, and probably *after* PR #280 merges and you've lived with the new logging a bit.

**The one decision to make before building** (I have a recommendation):
how loud is the per-request wide line? The standard's §5 says "wide line = INFO," but §4
says "reads never log at INFO" — and always-INFO would re-flood the poll noise we just
killed. **My recommendation:** wide line is INFO for state-changing requests
(POST/PUT/PATCH/DELETE) and any non-2xx, DEBUG for successful GETs — correlation still
binds on every request regardless. Confirm that (or pick always-INFO) and it's a
"build it" away.

## To pick back up tomorrow

- Review/merge **PR #280** (or ask for a walkthrough of any commit).
- Optional: decide whether to delete the two dead files (`app/seed.py`,
  `app/ingest_jobsites.py`) — 163 prints of dead code left untouched.
- When ready for the next piece: say **"build the §5/§7 work"** and confirm the
  wide-line level policy above. The full outline is in the chat history.
