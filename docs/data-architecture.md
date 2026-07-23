# Data Architecture

Status: **proposed** (design + forward plan). Companion operational doc:
[`backup-and-dr-runbook.md`](./backup-and-dr-runbook.md).

This is the coherent, whole-system view of where MileHigh's data lives, who owns
each piece, how it is protected, and where it is heading. It exists because the
data story had grown by accretion — Postgres, ephemeral disk, three external
systems of record, and a half-built data lake — with no single document tying
them together and no backup/DR story at all.

Read this for the *what and why*. Read the runbook for the *how to operate and
recover*.

---

## 1. Current state (as of 2026-07)

### 1.1 Compute / deploy

- **Everything runs in one Render web service.** Flask (Gunicorn, `wsgi.py`) plus
  the React build served as static files from `frontend/dist/`.
- **No separate worker/cron service.** Background work runs *in-process*:
  APScheduler jobs (`init_scheduler()` in `app/__init__.py`) and the
  `outbox_retry_worker` daemon thread. Scheduler duplication across Gunicorn
  workers is avoided with the `WERKZEUG_RUN_MAIN` / `IS_RENDER_SCHEDULER` guard.
- **No infrastructure-as-code.** There is no `render.yaml`, `Procfile`, or
  Dockerfile in the repo — the Render service, its env vars, and (if any) its
  persistent disk are configured only in the Render dashboard. **This means the
  Render config itself is a single point of failure that git does not protect.**
  See §6.

### 1.2 Data stores

| Store | Engine / location | What it holds | Durability today |
|---|---|---|---|
| **Operational DB** | Render managed **PostgreSQL**, one per env (`*_DATABASE_URL`) | `releases`, `projects`, `submittals`, `*_events`, `*_outbox`, `users`, board, notifications, **lake bronze** | Render's own storage; **no offsite copy, no in-repo backup automation** |
| **On-disk blobs** | Local container FS under `*_STORAGE_ROOT` | Marked-up PDFs, release/board photos, material-order email attachments | **Ephemeral unless a Render persistent disk is mounted** (`.gitignore` calls `app/storage/` "ephemeral on Render") |
| **App log file** | `logs/app.log` (rotating, 10MB×5) | Structured JSON logs | Ephemeral; also on stdout |
| **Repo data files** | `docs/jobsites.json`, `data/*.csv`, `snapshots/*.pkl` | Derived/config data | In git or regenerable |

Postgres connection is per-environment and SSL-required; pooling is tuned for
Render's ~5-min idle timeout (`app/db_config.py`). Tests are hard-forced to
in-memory SQLite (`TESTING=1`) and can never touch a real DB.

### 1.3 Systems of record

Three external systems feed the app; the boundary of "who owns the truth" is the
single most important thing to get right before designing backups.

| Domain | System of record today | Direction of travel |
|---|---|---|
| **Job log / scheduling** | The app's own Postgres (`releases`, `projects`) | Already authoritative; Trello is now a *mirror* the app writes **to** |
| **Installer board** | **Trello** (cards) | Being subsumed by the app DB via `TrelloOutbox` |
| **Submittals / ball-in-court / FC PDF packs** | **Procore** | ⚠️ **Contract ends Oct 2026** — must be extracted before then (see §4) |
| **Raw external comms (email)** | App DB **lake bronze** (`raw_source_records`) | The emerging durable record for the `bb@mhmw.com` mailbox |

Practical implication: **Postgres is the crown jewel.** Trello and Procore data
that has been ingested into the app DB is protected by protecting Postgres.
Blobs on disk (PDFs/photos/attachments) are the *second* priority because they
are referenced by DB rows but not reconstructable from them.

### 1.4 The "Hive Mind" data lake

A real but **bronze-only, dormant** lakehouse-lite lives at `app/lake/`
(`RawSourceRecord`, `LakeIngestState`, `graph_subscriptions`; migration
`migrations/add_lake_tables.py`). It is "lakehouse-lite **on Postgres**" — not
S3, not an external warehouse. The design intends bronze → silver → gold layers
for the Banana Boy traceback feature, but only **bronze** exists. Ingestion
(M365 mail pull + Graph push) is code-complete and gated off
(`BB_MAIL_INGEST_ENABLED`, default off), **blocked on client Azure admin
consent** (`docs/bb-email-ingestion.md`). No silver/gold, no external object
store, `boto3` is not yet a dependency.

---

## 2. Target architecture

The guiding principle: **one canonical operational database, one object store,
and a clear medallion lake — each with a protection story.** Nothing exotic; the
value is in coherence and in closing the backup gap.

```
                    ┌────────────────────────────────────────────┐
   External         │              Render web service            │
   systems          │   Flask + APScheduler + outbox worker      │
   ─────────        │                                            │
   Trello  ───────▶ │  ingest / webhooks / outbox                │
   Procore ───────▶ │        │                    ▲              │
   M365    ───────▶ │        ▼                    │ serve        │
                    │  ┌──────────────┐   ┌────────────────┐     │
                    │  │  Postgres    │   │ Object store    │◀───┼── NEW
                    │  │ (crown jewel)│   │ (blobs + lake)  │     │
                    │  │  bronze lake │   │  = Cloudflare R2│     │
                    │  └──────┬───────┘   └───────┬─────────┘     │
                    └─────────┼───────────────────┼──────────────┘
                              │                    │
              ┌───────────────┴───┐      ┌─────────┴─────────┐
              ▼                   ▼      ▼                   ▼
       Render managed      Nightly pg_dump   Blob writes    Lake silver/gold
       PITR backups   +    → R2 (offsite)    (PDF/photo/    (Parquet/tables,
       (primary DR)        (portability DR)   attachment)    later)
```

### 2.1 Object store: Cloudflare R2 (recommended, one bucket namespace)

You asked for the offsite backup target to be wherever the blob storage for
email/photo/PDF lives. **Recommendation: Cloudflare R2** as a single S3-compatible
store serving *both* roles, split by key prefix:

```
r2://milehigh-data/
  backups/
    postgres/prod/2026/07/23/milehigh-prod-2026-07-23T0700Z.dump
    postgres/sandbox/...
    disk/prod/2026/07/23/blobs-2026-07-23T0700Z.tar.zst   # optional, see runbook
  assets/
    pdfs/<release_id>/v<n>.pdf
    photos/<release_id>/<photo_id>.<ext>
    order-attachments/<sha256>.pdf
```

Why R2:

- **S3-compatible API** → drops straight into the existing swap-points. Every
  storage module already documents itself as "single swap point — replace these
  functions to migrate to OneDrive/S3" (`app/brain/job_log/features/pdf_markup/storage.py`,
  `.../photos/storage.py`, `app/brain/board/photos/storage.py`,
  `app/brain/material_orders/attachment_store.py`). `boto3` against R2 is the
  smallest possible change.
- **Zero egress fees** — matters for both restores (you pull the whole dump back)
  and for serving assets to the app.
- **Cheap at rest**, versioning + lifecycle rules for retention, object-lock
  available for ransomware-resistant immutable backups.

Alternatives if you'd rather: **Backblaze B2** (equivalent, also S3-compatible,
slightly cheaper storage); **AWS S3** (deepest ecosystem, Glacier tiering, but
egress costs on restore). Microsoft OneDrive/M365 was considered (you already use
Graph) but is a poor fit for programmatic backup/asset storage — no S3 API, weak
lifecycle/immutability — so it's not recommended for this role.

### 2.2 Blob migration: disk → R2 (removes the ephemerality risk entirely)

Today PDFs/photos/attachments live on the container FS and are **lost on recycle
unless a Render persistent disk is mounted**. Two ways to make them durable, in
priority order:

1. **Short term (do now): mount a Render persistent disk** and point
   `PDF_STORAGE_ROOT` (e.g. `/var/data/pdfs`; `PHOTO_STORAGE_ROOT` derives the
   sibling `photos`) and `MATERIAL_ORDER_STORAGE_ROOT` at it. This stops data
   loss immediately with zero code change. The disk then needs its own backup
   (runbook §3).
2. **Target: move blobs to R2** via the existing swap-points. Once assets live in
   R2, they are already offsite and versioned, and the "persistent disk backup"
   problem disappears — the disk stops holding anything you can't rebuild. This
   is the preferred end state; the persistent disk becomes a cache at most.

Either way, **the DB row is the index and the blob is the payload** — a restore
must bring both back to a consistent point (runbook §5.3).

### 2.3 The lake: finish the medallion, keep it on Postgres for now

- **Bronze** (`raw_source_records`) stays as-is: immutable, append-only, one row
  per raw external record. It is backed up as part of Postgres — no special
  handling.
- **Silver** (normalized, deduped, typed entities) and **gold** (serving
  views/marts for Banana Boy traceback and analytics) are still backlog. Build
  them as Postgres tables/materialized views first; only graduate to
  Parquet-in-R2 if/when volume or analytical workload justifies it. Do not stand
  up an external warehouse speculatively.
- **Attachments** referenced by bronze rows should land in `assets/` in R2
  (§2.1), not on ephemeral disk — this is the `docs/bb-email-ingestion.md`
  "stash attachments to R2/S3" note, now with a concrete home.

### 2.4 What stays exactly as it is

- Per-env Postgres selection and pooling (`app/db_config.py`) — correct, leave it.
- The idempotent standalone migration convention (`migrations/README.md`) — the
  backup story does **not** introduce Alembic.
- In-process scheduler/outbox model — fine at current scale.

---

## 3. Backup & disaster-recovery strategy (summary)

Full procedures, commands, and schedules live in the
[runbook](./backup-and-dr-runbook.md). The strategy in one paragraph:

**Two independent layers for the database.** (1) *Primary:* Render managed
Postgres **point-in-time recovery** — enable it (requires a paid Postgres plan),
it gives near-zero-RPO recovery inside Render with no code to maintain. (2)
*Defense-in-depth & portability:* a scheduled **`pg_dump -Fc` to R2**, retained
on a tiered schedule, so a full logical copy of the data lives **outside Render's
blast radius** and can be restored anywhere (this is also the Procore-style
"get our data out" insurance). **Blobs** are protected by moving them off
ephemeral disk (§2.2) — persistent disk plus, ideally, R2 as the store of record.

Proposed objectives (confirm in the runbook):

| | Target | Floor (must never exceed) |
|---|---|---|
| **RPO** (max data loss) | ~5 min via PITR | 24 h via nightly dump |
| **RTO** (time to restore) | < 2 h | < 1 business day |

---

## 4. Procore data exit (Oct 2026 forcing function)

`docs/ops-planning.md` flags this as an **unowned, no-plan, hard-deadline** risk:
the Procore contract ends **October 2026** and the submittal/ball-in-court/FC-PDF
data must be pulled out before access lapses. It belongs in the data architecture
because it is fundamentally a *data-custody migration*, and the target
architecture above is exactly where that data should land.

Plan of record (needs an owner and a date):

1. **Inventory** what Procore holds that the app does *not* already mirror into
   `submittals` / `submittal_events`. Much may already be in Postgres; confirm.
2. **Export** the rest via the Procore API (and any document/PDF assets) into:
   Postgres rows for structured data, `assets/` in R2 for documents.
3. **Snapshot** — take one authoritative `pg_dump` + R2 asset sync *after*
   extraction completes and store it with `object-lock` retention, so there is an
   immutable "as of contract end" copy.
4. **Verify** with the same restore drill used for DR (runbook §6).

This should be scheduled to *complete* well before Oct 2026, not started then.
Owner: **TBD — needs assignment.**

---

## 5. Testing backup & recovery

A backup you have never restored is a hypothesis, not a backup. The concrete,
repeatable drill lives in the runbook (§6): restore the latest prod dump into the
**sandbox** environment (the safe, existing target — `SANDBOX_DATABASE_URL`),
run the app against it, and verify row counts and referential integrity against
prod. This reuses the exact mechanism already proven by
`migrations/copy_prod_to_sandbox.sh`, but sourced from a *backup artifact* rather
than a live prod dump — which is what makes it a recovery test rather than a
clone. Cadence: **quarterly**, and once immediately after this plan lands.

---

## 6. Code & config: do we need backups outside GitHub?

**Source code: no dedicated backup needed.** GitHub is durable and every clone is
a complete history; the practical risks are *account/org loss* and *provider
outage*, not data loss. A cheap mitigation covers both without treating it as a
pillar:

- Enable a **scheduled read-only mirror** of the repo to a second location (a
  second git host, or a periodic `git clone --mirror` bundle pushed to
  `r2://milehigh-data/backups/code/`). Low effort, closes the org-loss gap.

**The real gap is everything that is *not* in git:**

- **Render dashboard configuration** — the service definition, build/start
  commands, persistent disk mounts, and cron settings exist only in Render.
  *Mitigation:* adopt **`render.yaml` (Blueprint) in the repo** so the
  infrastructure is version-controlled and reproducible. This is the highest-value
  "backup" item after the database.
- **Secrets / environment variables** — `*_DATABASE_URL`, Procore/Trello/Graph/
  Anthropic/Recall credentials live only in Render env. They are correctly *not*
  in git. *Mitigation:* keep a maintained, access-controlled secrets inventory
  (a `docs/` checklist of *which* vars must exist per env — names only, never
  values) plus an encrypted vault export held by the owner, so a rebuild-from-
  scratch is possible.

So: don't back up code beyond a low-cost mirror; **do** version the Render
config and document the secret inventory — those are the things whose loss would
actually stop a rebuild.

---

## 7. Prioritized roadmap

| # | Item | Why | Effort |
|---|---|---|---|
| 1 | Enable Render managed Postgres **PITR** (paid plan) | Primary DR, near-zero RPO, no code | Dashboard only |
| 2 | **Mount a persistent disk**, point `*_STORAGE_ROOT` at it | Stops blob loss on recycle *today* | Dashboard + env vars |
| 3 | Scheduled **`pg_dump → R2`** + retention + restore drill | Offsite portability; Procore-exit insurance | New cron + runbook |
| 4 | Commit **`render.yaml`** + secrets inventory doc | Config is currently un-backed-up | Small |
| 5 | Migrate blobs **disk → R2** via existing swap-points | Durable, offsite, versioned assets | Medium |
| 6 | **Procore export** into Postgres + R2, immutable snapshot | Hard Oct-2026 deadline | Medium/large, unowned |
| 7 | Lake **silver/gold** on Postgres | Unblocks Banana Boy traceback | Backlog |

Items 1–4 are the backup/DR foundation and should land first. 5–7 are the
architecture build-out.
