# Database Migration Context Doc
Confirming migration setup.
We will dump prod db to sandbox db and run migration suite on sandbox db for testing.

# Completely New Tables
## reference models.py on this branch
User
Release Events
Submittal Events
Procore/Trello Outboxes
Project Manager
Jobs ('job_sites) --> Projects
Webhook Receipt
SysLogs

# Migrating Tables
ProcoreSubmittals -> Submittals
ProcoreToken
Jobs

# Deprecating Tables
SyncOp
SyncLog
Job Changelog
Procore Webhook Events

# Issues
- I want to clean up the Submittals table in models.py. Would like to refactor some of those functions, more like how old_models.py has ProcoreSubmittals table.
- Want to confirm where SysLogs is implemented to make sure table is not unused.
- Want to rename model, table and implementations for 'job_sites' table. Model should be Projects, table name 'projects', implemented as such.
- Want to confirm Jobs 'jobs' and Releases 'releases'. Need both tables, with old_models.py jobs seeding 'releases' on rebuild script.