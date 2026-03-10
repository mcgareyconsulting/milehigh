-- M2: Rename procore_submittals → submittals and add missing columns
-- HIGH RISK — take a full DB backup and verify row counts before and after.
-- Run AFTER M1.

-- STEP 1: Verify row count before rename (run manually and record)
-- SELECT COUNT(*) FROM procore_submittals;

-- STEP 2: Rename the table
ALTER TABLE procore_submittals RENAME TO submittals;

-- STEP 3: Add any missing columns (IF NOT EXISTS guards — safe to re-run)
ALTER TABLE submittals ADD COLUMN IF NOT EXISTS was_multiple_assignees BOOLEAN DEFAULT FALSE;
ALTER TABLE submittals ADD COLUMN IF NOT EXISTS due_date DATE;
ALTER TABLE submittals ADD COLUMN IF NOT EXISTS order_number FLOAT;
ALTER TABLE submittals ADD COLUMN IF NOT EXISTS notes TEXT;
ALTER TABLE submittals ADD COLUMN IF NOT EXISTS submittal_drafting_status VARCHAR(50) NOT NULL DEFAULT '';
ALTER TABLE submittals ADD COLUMN IF NOT EXISTS ball_in_court VARCHAR(255);

-- STEP 4: Verify row count after rename (should match step 1)
-- SELECT COUNT(*) FROM submittals;
