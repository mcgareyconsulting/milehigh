# The Brain — Projects Page Design Specification

**Version:** 1.0  
**Date:** July 22, 2026  
**Author:** Bill O'Neill, Director of Operations — Mile High Metal Works  
**For:** Daniel McGarey, Developer

---

## Overview

The Projects Page is the central hub for Project Managers and company leadership to get a real-time overview of any active project. Every data point on this page is pulled live from The Brain's data layer. The page is designed to be scannable at a glance and drillable on demand.

---

## Layout & Interaction Model

- **Grid layout:** 3-column responsive grid
- **Drag-and-drop:** Every panel (card) is repositionable via a drag handle (⠿) in the top-left corner. Card positions are saved per user via `localStorage` so each person's layout persists across sessions.
- **Click-to-modal:** Clicking any panel header opens a full-detail modal overlay for that panel. Press Escape or click ✕ to close.
- **Color theme:** Dark mode — background `#0f1117`, surface `#1a1d27`, accent blue `#4f8ef7`

---

## Page Header

A sticky header bar at the top of the page containing:

| Element | Description |
|---|---|
| Project Number | e.g., `#450` |
| Project Name | e.g., `Sandstone Ranch` |
| GC Name | e.g., `PermaCorp Group of Companies` |
| Project Status Badge | Active / On Hold / Complete |
| Contract Value | e.g., `$847,320` |
| PM Name | e.g., `Danny Riddell` |
| Field Superintendent | e.g., `Scott Tatum` |

---

## KPI Summary Bar

7 numbers displayed horizontally below the header. These are the most important project health indicators at a glance:

| Metric | Source |
|---|---|
| Total Releases | Count of all releases on the project |
| FC Released | Count of releases at FC stage |
| In Drafting | Count of releases currently in drafting |
| Billed to Date | Sum of all approved Pay App line items |
| Remaining | Contract value minus billed to date |
| Open T&M Tickets | Count of T&M tickets not yet invoiced |
| CO Value Pending | Sum of change orders awaiting GC approval |

---

## Panel Specifications

### 1. Submittals

**Purpose:** Track all submittals sent to the GC for approval.

**Columns:** Submittal Name · Release Code · Submitted Date · Days Out · Status

**Status States:**

| Badge | Color | Meaning |
|---|---|---|
| Approved | Green | GC has approved — no action needed |
| Approved as Noted | Purple | GC approved with minor comments — review and act |
| Out to GC | Orange | Submitted, awaiting GC response — ball in their court |
| Overdue | Red | Past the 14-day standard review window |
| Rev. & Resubmit | Yellow | GC returned for revision — action required |
| In Prep | Gray | Drawings not yet submitted |

**Ball-in-Court Logic:**
- Day 9: Yellow warning — "5 days remaining in standard review window"
- Day 14: Orange overdue flag — Carmen sends automated follow-up email to GC contact
- Day 15+: Red OVERDUE badge — Carmen logs follow-up action in the panel

**Important:** DRR (Design Review Release) is an **internal approval only** — it does not appear in this panel and is never submitted to the GC.

---

### 2. Releases

**Purpose:** Show all production releases for the project with their current stage.

**Columns:** Release Name · 6-Digit Code · Product Type · Stage · Status

**Pizza Tracker (4-dot progress indicator):**

```
Draft → Shop → Paint → Install
  ●        ○       ○        ○   = In Drafting
  ●        ●       ○        ○   = In Shop
  ●        ●       ●        ○   = In Paint
  ●        ●       ●        ●   = Installed
```

**6-Digit Release Code format:** `[Project#]-[Release#]` e.g., `450-760`

---

### 3. Schedule

**Purpose:** Show all install dates for active releases.

**Date Types:**

| Badge | Color | Meaning |
|---|---|---|
| Hard Date | Green | GC-confirmed date — non-negotiable, highest priority |
| Projected | Yellow | Internally estimated — subject to change |

**Display:** Sorted by date ascending. Hard dates always appear above projected dates when on the same day.

---

### 4. Budget

**Purpose:** Show the financial health of the project by department.

**Rows:** Labor · Materials · Subcontractors · Equipment  
**Columns:** Budget · Spent · Remaining · % Used (progress bar)

**Footer:** Billed to Date · % of Contract Billed

---

### 5. T&M Tickets

**Purpose:** Track all Time & Material tickets for the project.

**Columns:** Ticket ID · Description · Date · Amount · Status

**Status States:** Draft · Submitted to GC · GC Approved · Invoiced

**Note:** T&M amounts feed into the monthly invoice once GC-approved. See T&M Module Build Doc for full workflow.

---

### 6. Rentals

**Purpose:** Track all equipment rentals charged to the project.

**Columns:** Equipment · Vendor · Start Date · End Date · Cost

**Vendors:** Sunbelt Rentals, United Rentals (data export integration planned — see PRD)

---

### 7. Change Orders

**Purpose:** All change orders for the project in one place. (Requested by Danny Riddell)

**Columns:** CO # · Description · Date Submitted · Amount · Status

**Status States:** Draft · Submitted · Approved · Rejected · On Hold

---

### 8. RFI Log

**Purpose:** Track all Requests for Information submitted to the GC.

**Columns:** RFI # · Subject · Submitted By · Date · Days Open · Status

**Note:** RFI ingestion strategy post-Procore cutoff (October) to be determined — manual entry or email parsing.

---

### 9. Punch List

**Purpose:** Track all punch list items for the project. (Requested by Rich Losasso)

**Columns:** Item # · Description · Owner · Due Date · Status (checkbox)

---

### 10. Project Contacts

**Purpose:** Quick-access contact directory for the project. (Requested by Rich Losasso)

**Rows:** GC PM · GC Superintendent · Architect · Structural Engineer · MHMW PM · MHMW Field Super · Key Vendors

---

### 11. Drawings

**Purpose:** Visual anchor for the project's architectural drawing set.

**Display:**
- Cover sheet image of the architectural set (uploaded by PM)
- Sheet index preview (first 5 sheets listed)
- Active Drawing Sets list with revision badges (Current / Reference)
- IFC revision badge in top corner

---

### 12. Project Notes

**Purpose:** Persistent PM notes that Carmen Miranda monitors and surfaces throughout the project lifecycle. (Full-width panel)

**Note Types:**

| Border Color | Type | Example Use |
|---|---|---|
| Orange | Follow-Up Required | "Do not close out 450-344 until closure plates are installed" |
| Blue | Contract Note | "O&P is 15% overhead, 10% profit per contract Exhibit B" |
| Green | Schedule Note | "GC look-ahead: Stair #2 area blocked until Aug 4" |
| Purple | Material Note | "Ultralox VE approved for 450-381 per RFI #12" |

**Carmen Miranda Integration:** Carmen monitors all notes. She surfaces relevant notes during billing cycles, drawing reviews, T&M ticket generation, and follow-up actions. Notes are never lost.

---

### 13. Project To-Do

**Purpose:** Project-scoped task list, individually assigned. (Full-width panel)

**Columns:** Task · Assigned To · Due Date · Priority · Status

**Rules:**
- To-do items are scoped to the specific project — they do not appear on other projects
- Items assigned to an individual appear on their Employee Home Page under "My Open Items"
- Overdue items display in red with a warning flag
- Completed items are grayed out with strikethrough text

**Footer:** Summary count by person and total open/overdue/completed

---

## Color Reference

```css
--bg:       #0f1117   /* Page background */
--surface:  #1a1d27   /* Card background */
--surface2: #22263a   /* Elevated elements */
--border:   #2a2d3e   /* Borders */
--accent:   #4f8ef7   /* Blue — primary action */
--green:    #22c55e   /* Success / Installed / Hard Date */
--yellow:   #f59e0b   /* Warning / Projected Date */
--red:      #ef4444   /* Overdue / Error */
--purple:   #a855f7   /* Approved as Noted / Material Notes */
--gold:     #f59e0b   /* Badges / Recognition */
--muted:    #6b7280   /* Secondary text */
```

---

## Files Included

| File | Description |
|---|---|
| `projects_page_mockup.html` | Fully interactive HTML mockup — open in any browser |
| `design_spec_projects_page.md` | This document — full panel specifications |

---

*The Brain — Mile High Metal Works Internal Operations Platform*
