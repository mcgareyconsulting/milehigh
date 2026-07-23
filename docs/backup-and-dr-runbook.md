# Backup & Disaster-Recovery Runbook

Status: **proposed**. Companion design doc:
[`data-architecture.md`](./data-architecture.md).

This is the operational half: exact procedures for backing up and restoring the
database and file assets, recovery-objective targets, and a repeatable
backup/recovery **test plan**. It assumes the object store from the design doc is
**Cloudflare R2** (`r2://milehigh-data/`, S3-compatible) — substitute any
S3-compatible bucket by swapping the endpoint.

> ⚠️ **Nothing in here has been provisioned yet.** Render's managed backups,
> persistent-disk mounts, and any scheduled job are configured in the Render
> dashboard, which is outside this repo. Treat the "Render dashboard" steps as a
> checklist for a human with dashboard access.

---

## 0. Recovery objectives

Confirm these; they drive every schedule below.

| Objective | Target | Hard floor |
|---|---|---|
| **RPO** — max acceptable data loss | ~5 min (PITR) | 24 h (nightly dump) |
| **RTO** — max time to full restore | < 2 h | < 1 business day |

Rationale: the operational DB (`releases`, `submittals`, events, outbox) is the
crown jewel; a day's loss of job-log edits would be painful but recoverable from
Trello/Procore/human memory, so 24 h is the floor and PITR pulls the real target
down to minutes. Blob assets (PDFs/photos) are not reconstructable, so once on
R2 their RPO equals the write (near-zero).

---

## 1. What we protect

| Asset | Where it lives | Backup mechanism | Priority |
|---|---|---|---|
| **Postgres** (all app + lake-bronze data) | Render managed PG per env | Managed PITR **+** `pg_dump → R2` | P0 |
| **Blob assets** (PDF/photo/attachment) | `*_STORAGE_ROOT` (disk) → R2 | Persistent disk + R2 (store of record) | P1 |
| **Render service config** | Render dashboard only | `render.yaml` in git (to adopt) | P1 |
| **Secrets / env vars** | Render env only | Access-controlled inventory + vault export | P1 |
| **Source code** | GitHub | Clones + optional mirror to R2 | P2 |
| **App logs** | `logs/app.log` + stdout | Ship stdout to a log sink (existing) | P3 |

---

## 2. Database backups

### 2.1 Layer 1 — Render managed PITR (primary)

**One-time, in the Render dashboard**, for the production Postgres instance (and
sandbox if you want it protected):

1. Ensure the instance is on a **paid plan** that includes point-in-time recovery
   / automated backups (free-tier instances do not).
2. Confirm the backup retention window shown in the dashboard meets §0 (e.g. 7
   days PITR).
3. Record, in this file under §7, the exact plan and retention window in force.

Recovery from this layer is a dashboard operation ("restore to a point in time"),
which provisions a **new** database. See §5.1.

### 2.2 Layer 2 — logical `pg_dump` to R2 (offsite, portable)

This is defense-in-depth: a self-contained logical dump that lives outside
Render and can be restored anywhere. It reuses the exact dump flags already
proven in `migrations/copy_prod_to_sandbox.sh` (`-Fc --no-owner --no-acl`).

**Manual dump + upload** (what the scheduled job automates):

```bash
# Requires: pg_dump (v16+ to match Render PG), awscli or rclone configured for R2.
# DATABASE_URL / PRODUCTION_DATABASE_URL comes from the Render env or your .env.
STAMP=$(date -u +%Y-%m-%dT%H%MZ)
OUT="/tmp/milehigh-prod-${STAMP}.dump"

pg_dump --no-owner --no-acl -Fc "$PRODUCTION_DATABASE_URL" -f "$OUT"

# Upload to R2 (S3-compatible endpoint). Example with awscli:
aws s3 cp "$OUT" \
  "s3://milehigh-data/backups/postgres/prod/$(date -u +%Y/%m/%d)/$(basename "$OUT")" \
  --endpoint-url "$R2_ENDPOINT"

rm -f "$OUT"          # never leave dumps (they contain all data) on the box
```

**Do**: mask credentials in any logs (log the DB host, never the URI — same rule
as `app/__init__.py`). **Never** print `$PRODUCTION_DATABASE_URL`.

**Where to schedule it** (pick one):

- **Render Cron Job service** (recommended) — a separate Render "Cron Job" that
  runs the script daily. Keeps it off the web dyno and independent of app health.
- **APScheduler in-process** — technically possible (the app already runs
  APScheduler), but a backup should not depend on the web service being healthy,
  so a separate cron is better.
- **External scheduler** (GitHub Actions on a schedule) — works, but then the
  prod DB URL must be a CI secret; acceptable if the Render cron option is
  unavailable.

**Retention (R2 lifecycle rules on the `backups/postgres/` prefix):**

| Tier | Keep |
|---|---|
| Daily | 14 days |
| Weekly (Sunday) | 8 weeks |
| Monthly (1st) | 12 months |
| Procore-exit / annual snapshot | indefinite, **object-lock** (immutable) |

Enable **bucket versioning** and, for the monthly/annual tier, **object-lock** so
a compromised credential cannot delete history.

### 2.3 Verifying a dump without restoring

A dump that won't list is worthless. The cron should assert the dump is readable
before it uploads:

```bash
pg_restore --list "$OUT" > /dev/null && echo "dump OK" || { echo "CORRUPT DUMP"; exit 1; }
```

---

## 3. Blob-asset backups

Blobs are the PDFs, photos, and material-order attachments written under
`PDF_STORAGE_ROOT` / `PHOTO_STORAGE_ROOT` / `MATERIAL_ORDER_STORAGE_ROOT`.

**Preferred end state (design doc §2.2):** the app writes blobs directly to R2
via the storage swap-points, so they are *already* backed up (versioned, offsite).
No separate blob backup job needed.

**Until that migration lands**, if blobs live on a mounted Render persistent
disk, back the disk up nightly:

```bash
# On a box with the disk mounted at /var/data:
STAMP=$(date -u +%Y-%m-%dT%H%MZ)
tar -C /var/data -cf - pdfs photos order-attachments \
  | zstd -q -o "/tmp/blobs-${STAMP}.tar.zst"
aws s3 cp "/tmp/blobs-${STAMP}.tar.zst" \
  "s3://milehigh-data/backups/disk/prod/$(date -u +%Y/%m/%d)/blobs-${STAMP}.tar.zst" \
  --endpoint-url "$R2_ENDPOINT"
rm -f "/tmp/blobs-${STAMP}.tar.zst"
```

Retention: mirror the DB daily/weekly tiers (14 days / 8 weeks). Blobs are
append-mostly and content-addressed (attachments are sha256-keyed), so an
incremental `aws s3 sync` of the disk into `assets/` is a cheaper alternative to
tarballs once volume grows.

> **Consistency note:** DB rows are the index into the blobs. When you back up,
> the dump and the blob copy should be close in time; on restore, a blob
> referenced by a row must exist. The restore drill (§6) checks for dangling
> references.

---

## 4. Config, secrets, and code (see design doc §6)

- **`render.yaml`** — adopt an Infrastructure-as-Code Blueprint so the service,
  disk mount, and cron are in git. Until then, keep a manual export of the
  service settings attached to this runbook.
- **Secrets inventory** — maintain a names-only checklist of required env vars per
  environment (`PRODUCTION_DATABASE_URL`, `SANDBOX_DATABASE_URL`, Procore/Trello/
  Graph/Anthropic/Recall creds, `R2_ENDPOINT` + access keys, `*_STORAGE_ROOT`).
  Never commit values. Hold an encrypted vault export off-platform.
- **Code mirror** — optional weekly `git clone --mirror` bundle to
  `r2://milehigh-data/backups/code/`, or a mirror to a second git host.

---

## 5. Recovery procedures

### 5.1 Restore the database from Render PITR (fastest, in-Render)

1. Render dashboard → the Postgres instance → **Recovery / Restore** → pick the
   timestamp (just before the incident).
2. Render provisions a **new** database instance with a new connection string.
3. Update the affected environment's `*_DATABASE_URL` env var to the new instance
   and redeploy (or repoint), OR promote per Render's flow.
4. Validate with §5.3.

Use this for accidental deletes, bad migrations, or corruption where Render itself
is healthy. RTO: typically well under an hour.

### 5.2 Restore the database from an R2 `pg_dump` (portable, out-of-Render)

Use when you need a copy outside Render, when PITR window has passed, or during a
Render-wide outage (restore into any Postgres).

```bash
# 1. Fetch the chosen dump from R2
aws s3 cp "s3://milehigh-data/backups/postgres/prod/2026/07/23/milehigh-prod-2026-07-23T0700Z.dump" \
  /tmp/restore.dump --endpoint-url "$R2_ENDPOINT"

# 2. Sanity-check it lists
pg_restore --list /tmp/restore.dump | head

# 3. Restore into the TARGET database (a fresh/empty one, or a wiped sandbox).
#    --clean --if-exists lets it replace objects; drop this on a truly empty DB.
pg_restore --no-owner --no-acl --clean --if-exists -d "$TARGET_DATABASE_URL" /tmp/restore.dump

# 4. Run outstanding migrations in documented order (M1..M6) if the dump predates them.
# 5. Validate with §5.3, then rm -f /tmp/restore.dump
```

⚠️ **Never** restore into production over live data without a fresh dump of the
current state first — even a corrupt present is worth capturing before overwrite.

### 5.3 Post-restore validation (both paths)

```bash
# Row counts for the key tables (mirror of copy_prod_to_sandbox.sh's check)
psql "$TARGET_DATABASE_URL" <<'EOF'
  SELECT 'users' AS t, COUNT(*) FROM users
  UNION ALL SELECT 'releases', COUNT(*) FROM releases
  UNION ALL SELECT 'submittals', COUNT(*) FROM submittals
  UNION ALL SELECT 'release_events', COUNT(*) FROM release_events
  UNION ALL SELECT 'submittal_events', COUNT(*) FROM submittal_events
  UNION ALL SELECT 'raw_source_records', COUNT(*) FROM raw_source_records
  ORDER BY t;
EOF
```

Then: (1) compare counts against the source (prod, or the pre-incident figure);
(2) boot the app against the restored DB and load the Job Log + a submittal; (3)
if blobs were restored, spot-check that a PDF/photo referenced by a restored row
opens. Dangling-reference check (rows pointing at missing blobs) is part of the
drill in §6.

### 5.4 Restore blob assets

```bash
aws s3 cp "s3://milehigh-data/backups/disk/prod/2026/07/23/blobs-....tar.zst" \
  /tmp/blobs.tar.zst --endpoint-url "$R2_ENDPOINT"
zstd -dc /tmp/blobs.tar.zst | tar -C /var/data -xf -   # onto the mounted disk
```

If blobs already live in R2 `assets/` (target architecture), there is nothing to
restore — repoint the app's storage config at the bucket.

---

## 6. Backup & recovery TEST PLAN

**Principle: an untested backup is a guess.** This drill proves the whole chain —
dump → offsite → restore → app works — in a safe environment. It deliberately
reuses the sandbox path already proven by `migrations/copy_prod_to_sandbox.sh`,
but **sourced from a backup artifact in R2**, which is what makes it a *recovery*
test and not just a clone.

### 6.1 Environment

Target the **sandbox** database (`SANDBOX_DATABASE_URL`). It is the designed-safe
target, is already wiped/reloaded routinely, and `TESTING=1` guarantees the test
suite itself never touches it. **Never run the drill against production.**

### 6.2 Cadence

- **Once now**, immediately after this plan lands (establishes the baseline).
- **Quarterly** thereafter.
- **After** any change to the backup pipeline, the schema-migration process, or
  the storage layer.
- **After** the Procore export (design doc §4), as its acceptance test.

### 6.3 Procedure

1. **Pick an artifact.** Choose the latest `pg_dump` from
   `r2://milehigh-data/backups/postgres/prod/…`. Record its timestamp and size.
2. **Record source truth.** Capture prod's key-table row counts (§5.3 query
   against prod) at the artifact's timestamp for comparison.
3. **Wipe + restore sandbox** from the artifact:
   ```bash
   aws s3 cp "s3://milehigh-data/backups/postgres/prod/<path>.dump" /tmp/drill.dump --endpoint-url "$R2_ENDPOINT"
   pg_restore --list /tmp/drill.dump > /dev/null            # integrity gate
   psql "$SANDBOX_DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
   pg_restore --no-owner --no-acl -d "$SANDBOX_DATABASE_URL" /tmp/drill.dump
   ```
4. **Migrations.** Run any migrations newer than the dump, in documented order.
5. **Validate data** (§5.3) — sandbox counts must match the source truth from
   step 2 (allowing for writes between the dump time and the reading).
6. **Referential-integrity / dangling-blob check** — for a sample of releases and
   submittals with attachments, confirm the referenced blob key exists in R2
   `assets/` (or on the restored disk). Log any dangling references.
7. **App smoke test** — point a sandbox app instance at the restored DB; log in,
   open the Job Log, open a submittal, open a marked-up PDF and a photo.
8. **Measure RTO** — record wall-clock from step 3 start to step 7 pass. Compare
   against §0. If it exceeds the target, that's an action item, not a pass.
9. **Clean up** — `rm -f /tmp/drill.dump`.
10. **Log the result** in §7 (date, artifact, RTO, pass/fail, issues).

### 6.4 Pass criteria

- Dump passed `pg_restore --list` before restore.
- Restore completed with no errors; migrations applied cleanly.
- Row counts reconcile with source truth.
- No unexpected dangling blob references.
- App smoke test passes.
- Measured RTO within §0 target (or a filed action item if not).

### 6.5 Failure handling

Any failed step halts the drill and opens a board item (bug tracker). A failed
drill means the backup is **not** trustworthy — treat as P0 until the next drill
passes.

---

## 7. Log of provisioning decisions & drills

Fill in as steps are actually done (this is the durable record — a green drill
here is the only proof the backup works).

| Date | Item | Detail | By |
|---|---|---|---|
| _TBD_ | PITR enabled | plan / retention window | |
| _TBD_ | Persistent disk mounted | mount path / size | |
| _TBD_ | pg_dump→R2 cron live | schedule / retention | |
| _TBD_ | First recovery drill | artifact / RTO / result | |
