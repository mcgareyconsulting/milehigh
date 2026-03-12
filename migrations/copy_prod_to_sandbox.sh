#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Find repo root (directory containing this script's parent)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Load environment variables from .env
ENV_FILE="$REPO_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: .env file not found at $ENV_FILE${NC}"
    exit 1
fi

# Source .env variables (skip comments and empty lines, handle spaces around =)
while IFS= read -r line; do
    [[ "$line" =~ ^#.*$ ]] && continue  # Skip comments
    [[ -z "$line" ]] && continue         # Skip empty lines
    # Remove spaces around = sign: "KEY = value" -> "KEY=value"
    line=$(echo "$line" | sed 's/[[:space:]]*=[[:space:]]*/=/')
    export "$line"
done < "$ENV_FILE"

# Validate required variables
if [ -z "$DATABASE_URL" ] || [ -z "$SANDBOX_DATABASE_URL" ]; then
    echo -e "${RED}Error: DATABASE_URL or SANDBOX_DATABASE_URL not set in .env${NC}"
    exit 1
fi

# Safety check
echo -e "${YELLOW}WARNING: This will WIPE the sandbox database and replace it with prod data.${NC}"
read -p "Are you sure? This will WIPE sandbox DB [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo -e "${GREEN}Starting prod → sandbox DB copy...${NC}"

# Dump prod DB
echo "Dumping prod database..."
pg_dump --no-owner --no-acl -Fc "$DATABASE_URL" -f /tmp/prod_dump.dump

if [ ! -f /tmp/prod_dump.dump ]; then
    echo -e "${RED}Error: Failed to create dump file${NC}"
    exit 1
fi

echo -e "${GREEN}Prod dump created ($(du -h /tmp/prod_dump.dump | cut -f1))${NC}"

# Drop and recreate schema in sandbox
echo "Dropping and recreating sandbox schema..."
psql "$SANDBOX_DATABASE_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" > /dev/null

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to drop/recreate sandbox schema${NC}"
    exit 1
fi

# Restore dump to sandbox
echo "Restoring dump to sandbox database..."
pg_restore --no-owner --no-acl -d "$SANDBOX_DATABASE_URL" /tmp/prod_dump.dump

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to restore dump to sandbox${NC}"
    exit 1
fi

# Verify - print row counts for key tables
echo -e "${GREEN}Verifying copy success - row counts in sandbox:${NC}"
psql "$SANDBOX_DATABASE_URL" << 'EOF'
  SELECT 'users' AS table_name, COUNT(*) AS row_count FROM users
  UNION ALL
  SELECT 'jobs', COUNT(*) FROM jobs
  UNION ALL
  SELECT 'releases', COUNT(*) FROM releases
  UNION ALL
  SELECT 'submittals', COUNT(*) FROM submittals
  UNION ALL
  SELECT 'submittal_events', COUNT(*) FROM submittal_events
  UNION ALL
  SELECT 'release_events', COUNT(*) FROM release_events
  UNION ALL
  SELECT 'job_sites', COUNT(*) FROM job_sites
  ORDER BY table_name;
EOF

# Clean up
rm -f /tmp/prod_dump.dump

echo -e "${GREEN}✓ Prod → Sandbox copy complete!${NC}"
echo "Next: Run migrations/M1-M7 in order against sandbox database"
