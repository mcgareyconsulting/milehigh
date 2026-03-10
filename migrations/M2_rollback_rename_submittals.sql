-- M2 ROLLBACK: Rename submittals → procore_submittals
-- Run this to undo M2 if needed.

ALTER TABLE submittals RENAME TO procore_submittals;
