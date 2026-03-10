# Feature Name / Description
DWL Urgency and Ordering
Removing drag n drop functionality from drafting work load. Replacing with single step
up/down arrows and bump toggle functionality.

# UI Location
The Drafting Work Load is the target UI page. The Up/Down arrows are row specific and should be rendered in the title column, central to the page.
The Bump button should remain where it is, next to the manual order number entry cell, per row.

# Backend Needs
Will probably need a single step urgency bump and resort function. Move submittal up 1 will have to move the one above it down 1, and vice versa. 
Each drafter will have 3 distinct submittal lists (Unordered, Ordered, and Urgent)
Bump button will toggle up only, so Unordered 'Bump' will push that submittal to x+1 of the Ordered column.
Bump button on Ordered will move that Submittal to 0.9 in urgency slots and bump urgents up as normal.


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
