# Handoff: MHMW Brain — Job Log Redesign (rail + table + release modal)

## Overview
Redesign of the MHMW Brain Job Log page: (1) top nav bar replaced with a collapsible icon rail, (2) the data table restyled to match the "job-log-review" print PDF (hairline grid, project banding, tinted flags), (3) a new release-detail modal with quick actions and threaded notes, (4) full light + dark themes.

## About the Design Files
`MHMW Brain.dc.html` in this bundle is a **design reference created in HTML** — a prototype showing intended look and behavior, **not production code to copy directly**. Recreate it in the existing MHMW Brain frontend using its established patterns, components, and table implementation. It runs in a browser if you want to interact with it (click rows, toggle rail/theme, post notes).

## Fidelity
**High-fidelity.** Colors, spacing, typography, and interaction states are final. Recreate pixel-perfectly with existing libraries. Data shown is sample data lifted from the real print; wire to the existing Job Log data source.

## Design Tokens
All values in `design-tokens.css`, both themes. Apply the theme by setting `data-theme="light|dark"` on the app root. Highlights (light):

- App canvas `#eef1f6`, surface `#ffffff`, raised surface `#f7f9fc`
- Table grid line `#b6bfcd` (1px everywhere; header bottom 1.5px), header bg `#e9edf4`
- Row bands: active zebra `#ffffff` / `#dcebfc`; **Install Complete rows** `#dde2ea` (de-emphasized grey)
- Row hover: overlay `rgba(30,90,200,.07)` (inset box-shadow so it works over any band)
- Stage tints: green `#0f6b46` on `#e6f5ec` · blue `#1a4fbd` on `#e8effc` · purple `#5b3bbd` on `#f0ebfc`
- Date flags (fill whole cell, bold): red/ASAP `#9e2b25` on `#f6d3d0` · green/hard date `#0c5f3e` on `#c6ead2` · amber `#8a5208` on `#f7e3ba`
- Accent `#2f5fd0`, accent tint `#e7eefc`
- Rail: bg `#16203a`, idle icon `#8e9db9`, active item `#2f5fd0` w/ white icon, hover `rgba(255,255,255,.08)`

Typography: **IBM Plex Sans** (UI) + **IBM Plex Mono** (numbers, dates, ids, version strings). Table body 12.5px (compact 12px); secondary cells 11.5px; header 12px/700; section labels 11px/700 uppercase, letter-spacing .06em.

## Screens / Views

### 1. Left rail (replaces top nav)
- Collapsed **60px**, expanded **212px**, `transition: width .18s ease`. `overflow: hidden`, **never scrolls** — content budget (logo 38 + 16 items × 38 + footer 3 × 37 + dividers) must fit; if more items are ever added, reduce item height rather than allowing scroll.
- Order: logo · divider · flat item list (Search, Map, Locations, Projects, **Job Log** (active), Drafting WL, Events, To-Dos, Install Schedule, Invoicing, Subs, Meetings, Bug Reports, T&M, Matching, Notifications) · divider · Collapse toggle, Theme toggle, Logout.
- Items: 37px tall, radius 8px, 19px stroke icons (1.7px stroke, round caps). Active = accent bg + white. Collapsed: centered icon + floating tooltip at `left: 66px`, vertically centered on the item (dark `#0b1220` bubble, 12px/500 white text, radius 7px, shadow, 120ms fade). Expanded: icon + 12.5px/600 label, badge moves inline right-aligned.
- Notifications badge: `#e0483c` pill, count, 2px rail-colored ring when collapsed.
- **Logo**: 38px rounded square, blue gradient `#3a6ae0→#22409a`, containing **`/assets/banana.svg`** (exists in the repo — do not recreate; prototype uses a stand-in glyph). Clicking opens the Patch Notes dialog. Expanded state shows "MHMW Brain" + "v2.0.322 · patch notes".

### 2. Patch notes dialog
- Centered card 520 × ≤80vh, radius 14px, sticky header (banana icon, "Patch notes", mono version chip, close).
- Entry: mono version + muted date, 12.5px body. Entries divided by hairlines.
- **Integration TODOs (stubbed in prototype, shown as a dashed box):**
  - `GET /api/v2/patch-notes` → `[{version, date, text}]`
  - Logo asset from `/assets/banana.svg`
  - Unread indicator when latest version > last-seen version (persist in localStorage)

### 3. Job Log page
- Header (52px): title + mono version, 300px search input, totals (Total / Fab HRS / Install HRS, mono bold), updated time, avatar.
- Toolbar: segmented Table/Cards/Auto · primary "New Release" (accent, plus icon) · secondary "Verbal" · Actions ▾ / Projects ▾ · filter chip row (28px pills; active = accent border + tint) · "Reset filters" (appears only when a chip/search is active) · segmented Table/Timeline.
- Table (the print-matched part):
  - `border-collapse: separate`, uniform 1px grid lines in `--grid`, header row sticky.
  - Header: bold dark centered text on `--head-bg`, 1.5px bottom rule.
  - **All cells center-aligned** (like the print). Numeric/date cells in Plex Mono. Description bold dark (not link-blue). Row height 36px (compact 28px).
  - **Banding rule:** rows with stage `Install Complete` get the grey band; all other rows zebra white/light-blue **counting only non-complete rows**.
  - Stage cell: tinted pill (radius 5px, 11.5px/600), hue by stage family — green (Paint*/Welded QC/Store/Ship Planning), purple (Install/Ship Complete), blue (everything else: Released, Fitup/Weld Start…). Keep existing stage→color mapping; do not invent new hues.
  - Date flag cells: whole cell filled with flag tint, bold mono text; optional sub-line (installer name) at 10.5px, 78% opacity.
  - Fab Order / Install Prog / Invoiced render as plain text (no boxed inputs).
  - Row hover: tint overlay + `cursor: pointer`; click opens the release modal.

### 4. Release detail modal
- Backdrop `rgba(10,16,28,.55)` + 2px blur; card `min(1180px, 94vw) × min(760px, 92vh)`, radius 14px, pop-in 180ms `cubic-bezier(.2,.8,.3,1)`.
- Header (raised surface): mono id chip `170-350` on accent tint · 17px/700 description · stage pill · muted context line (job · PM · detailed-by) · Events/Procore/Trello link buttons · close.
- Tabs: Details / Drawings & Photos (n) / Change Log — active = 700 weight + 2px accent underline.
- Quick-actions bar: primary **"Advance to {next stage}"** (advances along the stage ladder: Released → Fitup Start → Weld Start → Welded QC → Paint Start → Paint Complete → Ship Planning → Ship Complete → Install Start → Install Complete), plus Set ship date / Add note / Mark invoiced / Duplicate release. Right side: last-updated + source.
- Body grid `1fr 372px`:
  - Left: two columns of label/value rows (hairline separated, 8px vertical padding) grouped under uppercase section labels — Schedule (with ASAP/HARD mini-flags), Production, Assignment, Materials ordered (status pills reuse stage tints). Below: **stage progress ladder** — one 5px bar segment per stage; past = accent, current = stage color, future = grid grey.
  - Right (raised surface, own scroll): **Notes & activity** — threaded entries: 26px initial avatar, author 12.5px/700, mono timestamp, body 12.5px/1.45; replies indented 34px with a left rule and surface chip; "Reply" affordance on top-level entries. Composer pinned at bottom: textarea + "Post note" (disabled look at 45% opacity until text entered), "Replying to X · cancel" strip when replying.

## State Management
- `theme` ('light'|'dark'), `railOpen`, `patchOpen`, `selectedRelease`, `activeTab`, filter state (query + chip set), notes draft + replyTo, per-release note threads, stage override after "Advance".
- Search filters on job/rel/name/description/notes; record count in header reflects filtered set.

## Assets
- `/assets/banana.svg` — already in your repo; the prototype's inline glyph is a placeholder for it.
- Icons: 24-viewBox stroke icons (1.7px, round joins) — match to your existing icon set (Lucide-style).
- Fonts: IBM Plex Sans + IBM Plex Mono (Google Fonts or self-hosted).

## Files
- `MHMW Brain.dc.html` — interactive prototype (all screens/states)
- `design-tokens.css` — both theme palettes as CSS custom properties
