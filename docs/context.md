# Navbar Quick Search

## Current Implementation

### Search Bar
- Lives on the **Dashboard page** — rendered by `frontend/src/pages/DashboardPlaceholder.jsx` as a full-page wrapper around `frontend/src/components/QuickSearch.jsx`
- Accepts 1–3 digit job numbers (e.g. `4`, `40`, `400`). Prefix matching is supported, so typing `4` returns all 4xx jobs.
- 350ms debounce before the query fires
- Calls `GET /brain/job-search?job=<number>` via `frontend/src/services/jobSearchApi.js`

### Results Panel
- Rendered inline (not in a modal) inside `QuickSearch.jsx` as a full-screen-height overlay container with rounded corners and shadow
- Two-column grid layout: **Releases** on the left, **Submittals** on the right
- Table rows rendered by `frontend/src/pages/JobSearch/JobSearchTable.jsx`

### Jump To Button (`JobSearchTable.jsx:35–48`)
- **Releases** → navigates to `/job-log?job=<job>&release=<release>`, URL built from `row.job_release` (split on `-`)
- **Submittals** → navigates to `/drafting-work-load?highlight=<submittal_id>`
- On arrival, `frontend/src/hooks/useJumpToHighlight.js` scrolls the target `<tr>` into view and applies a 3.5-second yellow highlight

### Global Navbar (`AppShell.jsx`)
- Top bar: **MHMW Brain** title with gradient, no search input
- Hamburger icon (lines 38–47) toggles an animated sidebar overlay (lines 86–129)
- Sidebar links (`AppShell.jsx:6–11`):
  - `/dashboard` — Dashboard
  - `/events` — Events
  - `/drafting-work-load` — Drafting Work Load
  - `/job-log` — Job Log

### Backend Search Endpoint (`app/brain/job_log/routes.py:453–511`)
`GET /brain/job-search?job=<1-3 digits>`

Response shape:
```json
{
  "job": "400",
  "releases": [
    { "job_release": "400-A", "job": 400, "release": "A", "job_name": "...", "stage": "Released", "start_install": "<ISO date>" }
  ],
  "submittals": [
    { "submittal_id": "...", "title": "...", "status": "Open|Draft|Closed", "ball_in_court": "...", "submittal_drafting_status": "STARTED|NEED VIF|HOLD", "due_date": "<ISO date>", "days_since_ball_in_court_update": 0 }
  ]
}
```

---

## Desired Changes

### Primary — Move search to the global navbar
- Remove the search bar from the Dashboard page (`DashboardPlaceholder.jsx` / `QuickSearch.jsx`)
- Place the search input in the top bar of `AppShell.jsx`, immediately to the right of the hamburger menu button
- Results should still appear in the two-column (Releases | Submittals) table layout, now displayed as a modal/dropdown anchored to the navbar
- **Jump To behavior is unchanged** — same URL routing and `useJumpToHighlight` hook

### Secondary — Promote Job Log and Drafting Work Load to top-bar shortcuts
- Remove `/job-log` and `/drafting-work-load` from the `SIDEBAR_LINKS` array in `AppShell.jsx`
- Add them as visible navigation buttons in the top bar, flanking the **MHMW Brain** title
- Goal: one-click access without opening the hamburger menu

---

## Key Files

| File | Purpose |
|------|---------|
| `frontend/src/components/AppShell.jsx` | Global layout shell — navbar, hamburger, sidebar |
| `frontend/src/components/QuickSearch.jsx` | Search input, debounce logic, results panel |
| `frontend/src/pages/DashboardPlaceholder.jsx` | Dashboard page (currently hosts QuickSearch) |
| `frontend/src/pages/JobSearch/JobSearchTable.jsx` | Reusable table component with Jump To button |
| `frontend/src/hooks/useJumpToHighlight.js` | Scroll-and-highlight on Jump To navigation |
| `frontend/src/services/jobSearchApi.js` | `searchByJob(job)` — calls `/brain/job-search` |
| `app/brain/job_log/routes.py:453–511` | Backend search endpoint |
