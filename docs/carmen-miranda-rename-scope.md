# Rename scope: BB / BB01 / "Banana Boy" → Carmen Miranda

**Branch:** `update/carmen-miranda` · **Date:** 2026-07-23

Goal: rebrand the AI assistant persona from **BB / BB01 / "Banana Boy"** to
**Carmen Miranda**, with a new identity mailbox **`carmen_ai@mhmw.com`**
(replacing `bb@mhmw.com`).

## Decisions (locked with the client)

1. **Full rename, including the database** — table names, columns, persisted
   enum values, and env var names all move, not just display strings.
2. **Keep the banana theme.** Carmen Miranda *is* a banana motif (the fruit-hat),
   so the login `FloatingBananas` animation, the "Banana Code" stage-progress
   column, and the `banana_color` urgency flag **stay untouched**. They are MHMW
   mascot whimsy, not the bot.
3. **Both AI personas become Carmen** — the read-only chat assistant *and* the
   PDF code-compliance reviewer (both were branded "Banana Boy").

## What is explicitly OUT of scope (do not touch)

- **Procore "BB" = ball-in-court** (`app/procore/*`, submittal logic). Unrelated abbreviation.
- **Banana theme** (per decision 2): `FloatingBananas.jsx`, `StageIconRow.jsx` /
  "Banana Code" column, `stageProgress.js`, `banana_color` column +
  `add_banana_color_to_jobs.py` / `make_banana_urgency.py`.

---

## Tier A — External identity / Azure (highest risk; not code-only)

The mailbox move `bb@mhmw.com` → `carmen_ai@mhmw.com`. Long pole; needs tenant admin.

- [ ] Provision `carmen_ai@mhmw.com` in M365 (new mailbox or alias/rename of existing).
- [ ] Update the Exchange **Application Access Policy** that scopes the app-only
      Graph registration to a single mailbox — add/replace with the new address, or
      app-only reads + subscriptions fail with `ErrorAccessDenied`. *(Tenant config,
      not in this repo.)*
- [ ] Re-create the Graph mail change-notification **subscription** against the new
      mailbox resource path (`app/lake/scripts/ensure_subscription.py`,
      `create_subscription.py`); the old subscription is bound to the old address.
- [ ] Move the **Recall calendar mailbox** (the invite target the bot self-joins from).
- [ ] `.env` values on each environment: `BB_MAILBOX`, `RECALL_CALENDAR_MAILBOX`.
      ⚠️ `.env` is a symlink to the prod file — hand these edits to Daniel; do not
      apply to prod directly.

## Tier B — User-facing persona name (the actual rebrand; low risk)

Display strings only.

- [ ] `app/brain/meetings/recall.py:53,65` + `routes.py:70` — `bot_name="BB"` /
      default `'BB'` → `"Carmen Miranda"`. **This is the name shown in the Teams
      meeting — highest-visibility single change.**
- [ ] `frontend/src/components/BBChatWidget.jsx` — `"BB"` header, `"BB is thinking…"`,
      `"Ask BB — read-only data assistant"`, `aria-label` open/close, `"BB Chat access"`.
- [ ] `frontend/src/pages/ProjectDetail.jsx` + `frontend/src/data/projectsDemo.js` —
      "BB01 Project Brief", "BB01 Review", "confirmed by BB01" (all **BB01** refs).
- [ ] `frontend/src/components/bbReview/*` + `BBReviewPanel.jsx` — reviewer persona
      strings ("Banana Boy" review, status badges).
- [ ] `frontend/src/data/patchNotes.js`, `Login.jsx` copy, `frontend/index.html` title.
- [ ] Optional: rename the component files (`BBChatWidget.jsx` → `CarmenChatWidget.jsx`,
      `bbReview/` → `carmenReview/`) and their imports.

## Tier C — Internal code identifiers (full rename per decision 1)

### C1. Database — requires idempotent prod migrations (follow `migrations/README.md`)

Tables (rename `bb_*` → `carmen_*`):
- [ ] `bb_chat_conversations` → `carmen_chat_conversations`
- [ ] `bb_chat_messages` → `carmen_chat_messages`
- [ ] `bb_drawing_reviews` → `carmen_drawing_reviews`
- [ ] `bb_review_feedback` → `carmen_review_feedback`

Columns:
- [ ] `users.is_bb_chat` → `is_carmen_chat` (`app/models.py:64`)
- [ ] `notifications.bb_drawing_review_id` → `carmen_drawing_review_id` (`models.py:852`)

Constraints / FKs that embed the old name (rename with the tables):
- [ ] `_bb_review_feedback_finding_uc` (`models.py:1967`)
- [ ] `_bb_drawing_reviews_*` / `_bb_review_feedback_review_id` FKs.

**Persisted VALUES** (data, not schema — need an `UPDATE` backfill or dual-read):
- [ ] `ai_usage.feature = "bb_chat"` → `"carmen_chat"` (`bb_chat/service.py:82`)
- [ ] `ai_usage.entity_type = "bb_chat_message"` → `"carmen_chat_message"` (`service.py:92`)
- [ ] `notifications.type = "bb_review"` → `"carmen_review"` (`pdf_review/worker.py:177`).
      ⚠️ The frontend routes notification click-through on this string — update
      frontend + backfill existing rows together, or accept both values during transition.

> Migration risk is real (live-table renames + backfills). Use `IF EXISTS`,
> AUTOCOMMIT, `lock_timeout`, per the CLAUDE.md non-negotiables. `ALTER TABLE …
> RENAME` is metadata-only and fast; the `UPDATE` backfills touch row data — batch them.

### C2. Environment variable names

Rename `BB_*` → `CARMEN_*` (recommend keeping a `BB_*` fallback read for one deploy
so `.env` files can be updated without a flag-day):
- [ ] `BB_MAILBOX`, `BB_MAILBOXES`, `BB_INGEST_GROUP_ID`
- [ ] `BB_MAIL_POLL_MINUTES`, `BB_MAIL_INGEST_ENABLED`, `BB_MAIL_WEBHOOK_ENABLED`
- [ ] `BB_CHAT_MODEL`, `BB_CHAT_MAX_TOKENS`, `BB_CHAT_EFFORT`,
      `BB_CHAT_SQL_TIMEOUT_MS`, `BB_CHAT_SQL_ROW_LIMIT`, `BB_CHAT_MAX_STEPS`
- [ ] Update `.env` on every environment (hand to Daniel; prod symlink).

### C3. Module / file paths + symbols

- [ ] `app/brain/bb_chat/` → `app/brain/carmen_chat/` (+ blueprint name, imports, url_prefix).
- [ ] `pdf_review/` "BB" symbols → Carmen (module can stay `pdf_review`; strings/logs move).
- [ ] SQLAlchemy model classes: `BBDrawingReview`, `BBReviewFeedback`, `BBChat*` → `Carmen*`.
- [ ] Frontend services: `bbChatApi.js` → `carmenChatApi.js`.
- [ ] Logger event names `bb_review_*`, `bb_chat_*` → `carmen_*` (telemetry continuity — note in changelog).
- [ ] Migration filenames referencing `bb_` are historical; leave applied ones, name new rename scripts `rename_bb_to_carmen_*`.

## Tier D — Docs & comments (cosmetic; batch last)

`docs/feature-catalog.md`, `docs/ops-planning.md`, `docs/bb-email-ingestion.md`,
`docs/calendar-recall-scheduling.md`, `docs/bb-pdf-review-hardening-plan.md`,
`docs/feature-plan-2026-06-30.md`, `docs/order-tracking-scaffold.md`,
`docs/observability-guide.md`, `docs/tablet-tuning.md`, plus inline code comments
("BB (Banana Boy)"). No functional impact.

---

## Suggested execution order

1. **Tier A** provisioning first (mailbox + Azure access policy) — everything mail-side
   depends on it and it has external lead time.
2. **Tier C1 migration script** authored + reviewed (not yet run) alongside code that
   reads the new names with old-name fallback.
3. **Tier B** display rename (safe, shippable independently — could go first for quick win).
4. **Tier C2/C3** env + module rename with fallbacks.
5. Run migrations per environment (Daniel), flip `.env`, drop fallbacks in a follow-up.
6. **Tier D** docs sweep.

## Files touched (reference counts, this branch)

- `bb@mhmw` / mailbox refs: ~38 files
- `BB` token (excl. ball-in-court): ~80 files
- `BB01`: 3 files
- `banana` (mostly OUT of scope — theme): ~50 files, keep
