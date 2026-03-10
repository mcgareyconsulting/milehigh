# Feature Name / Description
Total Fab HRS - Total Install HRS
My client would like to see total fabrication hours and total installation hours
for jobs on the job log.

# UI Location
The Job Log has a filter header with various filter buttons. The bottom of that filter component
contains a reset filters button, the right side contains a last updated timestamp.
I would like for these two fields to populate on the right, internal side of the last updated at timestamp.

# Backend Needs
Scheduling directory will contain reusable calculations/functions.
Total Install Hours = sum of all jobs (install hours x job comp %)
Total Fab Hours = sum of all jobs (fab hours x modifier)
- modifier (if stage = cut, modifier = 10%; if stage = fitup, modifier = 50%; if stage = welded/qc, modifier = 0%)


# Relevant Directories
## Backend
app/brain/job_log/scheduling

## Frontend
frontend/src
frontend/src/pages/JobLog.jsx
frontend/src/hooks/useJobsDataFetching.js
frontend/src/hooks/useJobsFilters.js
frontend/src/service/jobsApi.js
