# Feature Name / Description
Resort on Drafter Filter

# UI Location
The Drafting Work Load is the target UI page. The filtering block at the top of the DWL lists out all drafters with submittals in either tab, Open or Draft. 
The Resort button is in the upper right of this header feature on the DWL.

# UI Needs
The resort button should be disabled when drafter filter is 'All'
Only active when we are filtering by a single drafter

# Backend Needs
The Resort button, which will compress the ordering of a drafter's submittal should be reworked to be drafter specific.
Resort will compress a drafters submittal order list for 'Ordered' submittals only. Urgency should be auto cascading. We want to force a resort of ordered submittals occasionally. Example: Drafter list is 4-5-6-7-8. Admin pushes resort with that drafter filtered and result is 1-2-3-4-5, preserving order.


# Relevant Directories
## Backend
app/brain/drafting_work_load
build in engine/routes/service style

## Frontend
frontend/src
frontend/src/pages/DraftingWorkLoad.jsx
frontend/src/hooks/useDataFetching.js
frontend/src/hooks/useFilters.js *I think*
frontend/src/service/draftingWorkLoadApi.js
frontend/src/components/TableRow.jsx
