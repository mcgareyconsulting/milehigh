#! /usr/bin/env bash
# This script is used to refresh the staging database.
# 
# Requirements:
#   - PostgreSQL client tools (pg_dump, pg_restore, psql) version 17.x or newer
#   - If you have an older version, upgrade with: brew install postgresql@17
#   - Or use Docker: docker run --rm postgres:17 pg_dump ...
set -e 

# Load environment variables from .env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

if [[ -z "$DATABASE_URL" || -z "$SANDBOX_DATABASE_URL" ]]; then
  echo "Missing DB URLs"
  exit 1
fi

echo "Prod DB:"
echo "$DATABASE_URL"
echo
echo "Staging DB:"
echo "$SANDBOX_DATABASE_URL"
echo

read -p "Type YES to continue: " CONFIRM
if [[ "$CONFIRM" != "YES" ]]; then
  echo "Aborted."
  exit 1
fi

# --- Step 1: Dump production DB ---
echo "Dumping production database..."

# Check pg_dump version compatibility
PG_DUMP_VERSION=$(pg_dump --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
echo "Local pg_dump version: $PG_DUMP_VERSION"

# Try to get server version from connection (if possible)
# Note: This is a best-effort check; the actual error will come from pg_dump
echo "Attempting dump (pg_dump will error if version mismatch)..."
pg_dump "$DATABASE_URL" \
  --format=custom \
  --no-owner \
  --no-acl \
  --verbose \
  > prod.dump || {
    echo ""
    echo "ERROR: pg_dump failed due to version mismatch."
    echo ""
    echo "Your local pg_dump version ($PG_DUMP_VERSION) is older than the server version (17.6)."
    echo ""
    echo "To fix this, upgrade PostgreSQL client tools:"
    echo "  brew upgrade postgresql@17"
    echo "  OR"
    echo "  brew install postgresql@17"
    echo ""
    echo "Then ensure the new version is in your PATH:"
    echo "  brew link --force postgresql@17"
    echo ""
    echo "Alternatively, you can use Docker:"
    echo "  docker run --rm -e PGPASSWORD=\$(echo \$DATABASE_URL | grep -oP 'password=\\K[^@]+') \\"
    echo "    postgres:17 pg_dump \$DATABASE_URL --format=custom --no-owner --no-acl > prod.dump"
    echo ""
    exit 1
  }

# --- Step 2: Reset staging schema ---
echo "Resetting staging database schema..."
psql "$SANDBOX_DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# --- Step 3: Restore dump into staging ---
echo "Restoring production dump into staging..."
pg_restore \
  --no-owner \
  --no-acl \
  --verbose \
  --dbname="$SANDBOX_DATABASE_URL" \
  prod.dump


echo "Staging refresh complete!"