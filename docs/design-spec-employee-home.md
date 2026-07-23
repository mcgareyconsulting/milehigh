# The Brain — Employee Home Page Design Specification

**Version:** 1.0  
**Date:** July 22, 2026  
**Author:** Bill O'Neill, Director of Operations — Mile High Metal Works  
**For:** Daniel McGarey, Developer

---

## Overview

The Employee Home Page is every team member's personal dashboard inside The Brain. It is personalized to the individual — their open items, their projects, their badges, their subscribed releases. It is also the social heartbeat of the company, surfacing photos, milestones, and recognition from across all active projects.

The goal is simple: **every employee opens The Brain in the morning and immediately knows what they need to do today, and gets to see what the team is building.**

---

## Layout & Interaction Model

- **Grid layout:** 3-column responsive grid
- **Drag-and-drop:** Every panel is repositionable via drag handle (⠿). Layout saved per user via `localStorage`.
- **Click-to-modal:** Every panel opens a full-detail modal on click.
- **Color theme:** Same dark theme as Projects Page.

---

## Page Header

Personalized hero header at the top of the page:

| Element | Description |
|---|---|
| Avatar | User initials in a colored circle |
| Greeting | "Good morning, [First Name] 👋" |
| Role & Company | e.g., "Lead Drafter · Mile High Metal Works" |
| Date | Current date |
| Earned Badges | Displayed as pill badges below the greeting |
| KPI Bar | 6 personal stats: Open Items · Due This Week · Completed This Month · Active Projects · Overdue Items · On-Time Streak |

---

## Panel Specifications

### 1. My Open Items

**Purpose:** Every task, review, submittal, and to-do assigned to this person across all projects.

**Item Types & Colors:**

| Badge | Color | Source |
|---|---|---|
| Review | Red | DRR or drawing review assigned to this person |
| Submittal | Blue | FC package or submittal they are responsible for |
| Task | Yellow | Task assigned from a project |
| To-Do | Gray | To-do item from a project's To-Do panel |

**Columns:** Type Badge · Item Name · Release Code & Note · Due Date (color-coded: red = overdue, orange = due soon, green = on track)

---

### 2. Company News Feed

**Purpose:** The social heartbeat of the company. Photo-forward. Shows installs, shop progress, badge awards, milestones, material updates, and Carmen alerts.

**Feed Item Types:**

| Tag | Color | Trigger |
|---|---|---|
| Install Complete | Green | Release marked Installed in Job Log |
| Photos | Purple | User posts photos to a release |
| Milestone | Gold | Production record, project completion, etc. |
| Badge | Gold | Employee earns a badge |
| Material Order | Blue | Subscribed material order status change |
| Alert | Red | Carmen Miranda automated alert |

**Photo Display Rules:**
- When a user posts photos to a release, the feed shows a **featured hero image** (full-width) for the most recent install
- Inline photo posts show a **3-thumbnail grid** directly in the feed
- Photos are linked to their release code so any employee can tap through to the full release

---

### 3. Work in Progress & Installed (Photo Gallery)

**Purpose:** Visual gallery of all active releases across all projects this employee is assigned to. The primary goal is to let shop and field workers see the **finished installed product** — closing the loop between fabrication and the real-world result.

**Filter Tabs:** All · ✓ Installed · ⚙ In Shop · 🎨 Paint · 📐 Drafting

**Display:**
- **Hero featured photo** — most recently installed release, full-width with project name and location
- **Thumbnail grid** — all other active releases, sorted by most recent photo
- **Upload Photos button** — any employee can upload photos from their phone directly to a release

**Photo source:** All photos are pulled from the Job Log release. When a photo is uploaded to a release in the Job Log, it automatically appears here.

---

### 4. My Release Tracker (Pizza Tracker)

**Purpose:** Subscribe to specific releases and watch them move through the production pipeline.

**Pizza Tracker stages:** Draft → Shop → Paint → Install

Each subscribed release shows:
- Release name and 6-digit code
- Current stage highlighted in the progress bar
- Stage label (In Drafting / In Shop / In Paint / Installed / Complete)

**Subscription:** Employee chooses which releases to follow. They receive a news feed notification when a release advances to the next stage.

---

### 5. Material Order Updates

**Purpose:** Subscribe to material orders on your projects and get live status updates.

**Columns:** Order Name · Release Code & Project · Vendor · Status

**Status States:** Ordered · Confirmed · Shipped · Delivered · Pending

---

### 6. My Badges & Recognition

**Purpose:** Display earned badges prominently and show progress toward locked badges to drive engagement.

**Earned badges:** Displayed with name, description, and date earned.

**Locked badges:** Displayed with progress counter (e.g., "8 to go", "87/100") to motivate the next milestone.

**Suggested Badge Set (starting point — add more as culture develops):**

| Badge | Trigger |
|---|---|
| 🏆 Zero-Error Week | 100% accuracy on all reviews in a week |
| ⚡ 5 FC Releases | 5 FC packages completed in one month |
| 🎯 On-Time Streak | N consecutive on-time deliveries |
| ⭐ Top Drafter | Highest output in a quarter |
| 🔥 20 FC Streak | 20 consecutive on-time FCs |
| 💎 Diamond Drafter | 100 total FCs completed |
| 🛡️ Zero Punch Items | No punch items on 5 consecutive jobs |
| 🚀 Speed Demon | FC package completed in under 3 days |
| 🍌 Banana Award | Recognized for setting teammates up for success |

**Note:** When a badge is earned, it automatically posts to the Company News Feed so the whole team sees it.

---

### 7. My Projects

**Purpose:** Quick-access list of all projects this employee is assigned to.

**Columns:** Project # · Project Name · Role · Active Release Count · Status Badge

---

### 8. My EOS Rocks

**Purpose:** Show this employee's current quarter Rocks with progress status. Links to the full EOS Module page.

**Display:**
- Carmen Miranda 🍌 banner with Q3 countdown
- Each Rock with 4-step progress bar: Defined → In Progress → Review → Complete
- On Track (green) / At Risk (yellow) / Off Track (red) status badge
- Footer: "N/N Rocks On Track · X days to L10"

**Carmen Integration:** Carmen monitors all Rocks and surfaces them in the weekly L10 meeting prep. She flags any Rock that moves to At Risk or Off Track and prompts the owner to update their status.

---

## Banana Award — Recognition System

The Banana Award (🍌) is MHMW's internal recognition for employees who exemplify **"setting each other up for success."** It ties directly into the monthly company meeting and the EOS culture.

**How it works:**
1. Any employee (or leader) can nominate a teammate for a Banana
2. The nomination includes a specific reason ("David caught a hardware error on 450-759 before it hit the shop floor")
3. The award posts to the Company News Feed
4. The recipient gets a 🍌 badge on their Employee Home Page
5. Bananas are tallied monthly and recognized at the company meeting

---

## Color Reference

Same as Projects Page — see `design_spec_projects_page.md`.

---

## Files Included

| File | Description |
|---|---|
| `employee_home_mockup.html` | Fully interactive HTML mockup — open in any browser |
| `design_spec_employee_home.md` | This document — full panel specifications |

---

*The Brain — Mile High Metal Works Internal Operations Platform*
