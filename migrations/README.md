# Migrations

There is no Alembic. A migration is a **standalone, idempotent Python script** in this
folder that infers its DB URL from `ENVIRONMENT`/`.env` (or `--database-url`) and brings
the schema forward. You run it **once per environment** (local → sandbox → production).

These scripts run against the **live production Postgres while the app is serving
traffic**. A careless one can take an `ACCESS EXCLUSIVE` lock and freeze the table for
every request behind it. The rules below are not style preferences — they are how we
avoid an outage. They were written after a migration froze `submittals` in prod.

## Reference template

Copy **`add_start_install_to_dwl.py`** for any column/table change. Copy
**`add_index_on_jobs_last_updated_at.py`** for a pure index add. Both already implement
the rules below; start from them rather than from scratch.

## Rules (Postgres)

1. **Idempotent DDL, no reflection.** Use `ADD COLUMN IF NOT EXISTS`,
   `CREATE TABLE IF NOT EXISTS`, `CREATE [UNIQUE] INDEX IF NOT EXISTS`. Because the DB
   enforces idempotency, the script needs **zero schema reflection**.
   - ❌ **Never** call SQLAlchemy reflection (`inspect(engine)`, `get_columns`,
     `get_table_names`) while a transaction is open holding a lock. Reflection grabs a
     *second* pooled connection; its catalog read blocks on the `ACCESS EXCLUSIVE` lock
     your *first* connection holds, and since the script is single-threaded waiting on
     that read, the first connection can never commit to release the lock. Postgres
     does **not** flag it as a deadlock (the holder is `idle in transaction`, not
     lock-waiting), so it hangs until app `statement_timeout`s start firing. This is
     exactly what took prod down.

2. **One AUTOCOMMIT connection.** Open a single connection with
   `execution_options(isolation_level="AUTOCOMMIT")` and run each statement on it. Each
   statement is its own implicit transaction, so an exclusive lock is held only for the
   instant the statement runs — never across the whole migration.

3. **`SET lock_timeout` + retry.** `SET lock_timeout = '5s'` so a blocked `ALTER` fails
   fast instead of queueing (a queued `ACCESS EXCLUSIVE` request blocks *every* later
   query on the table). Retry with backoff so transient contention self-heals. Also
   `SET statement_timeout` as a backstop.

4. **Keep `ADD COLUMN` metadata-only.** Nullable, no volatile default → instant. If you
   need a default/backfill, add the column first, backfill in batches in *separate*
   transactions, then add the constraint — never in one big locking statement.

5. **New tables are free.** A `CREATE TABLE` is invisible to other sessions until commit,
   so it and its indexes have no contention. The lock danger is only on existing,
   actively-queried tables (e.g. `submittals`, `releases`).

6. **Mask the DB URL in logs.** Print `scheme://user@host/db`, never the password.

7. **Idempotent + re-runnable.** Safe to run twice; a second run is a no-op.

## Pre-flight checklist

- [ ] Started from `add_start_install_to_dwl.py` (or the index template).
- [ ] All DDL is `IF NOT EXISTS`; no `inspect()` on the Postgres path.
- [ ] Single AUTOCOMMIT connection; `lock_timeout` set; retry/backoff present.
- [ ] `ADD COLUMN` is nullable with no volatile default.
- [ ] Ran it against a scratch SQLite DB (or local) twice — second run is a clean no-op.
- [ ] DB URL is masked in output.
- [ ] Model in `app/models.py` matches the DDL (column types, index names like
      `ix_<table>_<col>` for `unique=True, index=True`).

## Running

```bash
# Uses ENVIRONMENT + .env to pick the DB (production/sandbox/local)
python migrations/<name>.py

# Or target a DB explicitly
python migrations/<name>.py --database-url postgresql://...
```

Run per environment. For production, prefer a quieter traffic window — with
`lock_timeout` the script will fail fast and retry rather than hang, but a calm window
still gets it in on the first try.

## If a migration appears to hang (incident playbook)

A migration holding a lock blocks all queries on that table; the app's reads start
erroring with `canceling statement due to statement timeout`. To diagnose against
`pg_stat_activity` (safe — it doesn't touch the locked table):

```sql
-- the stuck backend + what it's blocking
SELECT pid, state, wait_event, now()-xact_start AS age, left(query,90)
FROM pg_stat_activity
WHERE query ILIKE '%<table>%' AND pid <> pg_backend_pid()
ORDER BY xact_start NULLS LAST;

-- blocking chains
SELECT pid, pg_blocking_pids(pid), state, left(query,80)
FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;
```

To release it: if the migration backend is `idle in transaction`, `pg_cancel_backend`
is a no-op (no running query to cancel) — use `pg_terminate_backend(<pid>)`, which drops
the connection and rolls back the uncommitted transaction (so the half-done DDL is
reverted cleanly). Then the app recovers on its own.
