# Job Log — styling document (shipped baseline)

**Pinned:** 2026-08-06 (restyle pass)  
**Purpose:** Source of truth for how the live Job Log looks *now*, aligned to the print PDF where color/type matter. Prefer this over the Aug 2026 handoff prototype when they disagree.

| Artifact | Path |
|----------|------|
| Design intent (pre-ship) | `docs/design/job-log-redesign/README.md` |
| Handoff tokens (historical) | `docs/design/job-log-redesign/design-tokens.css` |
| **Live tokens** | `frontend/src/styles/tokens.css` |
| Print PDF builder | `frontend/src/utils/jobLogPdf.js`, `pdfFonts.js` |
| Column widths | `frontend/src/utils/jobLogColumns.js` → `COLUMN_WIDTH_PERCENT` |
| Table body | `frontend/src/components/JobsTableRow.jsx` |
| Table shell / header | `frontend/src/pages/JobLogContent.jsx` |
| Filter chrome | `frontend/src/pages/ReleasesLayout.jsx` |
| Type / app chrome | `frontend/src/index.css`, `frontend/tailwind.config.js` |
| Reference PDF | e.g. `job-log-review-*.pdf` export from Review mode |

**Print is the color/type source of truth** for row bands, stage groups, and date flags. Screen density and chrome are app-specific.

---

## 1. Typography

### Faces

| Role | Face | Source |
|------|------|--------|
| UI / free text | **IBM Plex Sans** | `@fontsource/ibm-plex-sans` → `index.css`; Tailwind `font-sans` |
| Numbers, dates, ids | **IBM Plex Mono** | `@fontsource/ibm-plex-mono`; Tailwind `font-mono` |
| PDF embed | Same (TTF) | `frontend/public/fonts/*.ttf` via `scripts/build_pdf_fonts.py` |
| PDF fallback | Helvetica / Courier | If TTF load fails (`pdfFonts.js`) |

jsPDF names: `IBMPlexSans`, `IBMPlexMono`. CSS: `"IBM Plex Sans"`, `"IBM Plex Mono"`.

### Scale (screen)

| Token | Size | Use |
|-------|------|-----|
| `text-jl` | 12.5px / 1.2 | Body cells |
| `text-jl-compact` | 12px / 1.2 | Compact density |
| `text-jl-2` | 11.5px / 1.2 | Job name, paint, PM, BY |
| `text-jl-3` | 10.5px / 1.15 | Installer sub-line |
| `text-jl-head` | 12px / 1.15 | Column headers |
| `text-jl-label` | 11px / 1.2 + `.06em` | Modal section labels |

Print PDF body ~9pt, header ~9.5pt bold (denser; same families).

### Mono columns (screen + PDF)

`Job #`, `Release #`, `Fab Hrs`, `Install HRS`, `Released`, `Fab Order`, `Ship Date`, `Start install`, `Comp. ETA`, `Job Comp`, `Invoiced`.

Sans: Job, Description, Stage, Notes, Paint color, PM, BY, Mats, header row.

Keep `MONO_COLUMNS` in `jobLogPdf.js` in lockstep with `JobsTableRow`.

### Formatting notes

- **Fab / Install Hrs:** `toFixed(2)` → e.g. `12.00`, `108.00`.
- **Fab Order:** `formatFabOrder()` — placeholder **80.555** always three decimals; integers stay whole.
- **Hours columns:** `tabular-nums` + tight padding so long values stay centered.

---

## 2. Color tokens (light)

Live file: `frontend/src/styles/tokens.css` (`:root` / `.dark`).

### Surfaces & ink

| Token | Light | Role |
|-------|-------|------|
| `--bg` | `#eef1f6` | App canvas |
| `--surface` | `#ffffff` | White zebra / surfaces |
| `--head-bg` | `#e9edf4` | Table header |
| `--grid` | `#b6bfcd` | Lattice + frame |
| `--text` | `#0a0a0a` | Primary ink (≈ print black) |
| `--text-2` | `#1f2937` | Secondary |
| `--text-3` | `#4b5563` | Tertiary |
| `--accent` / brand | `#2f5fd0` | Links, active chrome |

### Row bands (= print)

| Class / token | Light | Print RGB |
|---------------|-------|-----------|
| `jl-band-a` / `--surface` | `#ffffff` | white (odd/even 0) |
| `jl-band-b` / `--band-b` | `#dbeafe` | `219, 234, 254` blue-100 |
| `jl-band-done` / `--band-done` | `#9ca3af` | `156, 163, 175` gray-400 |

**Banding rule:** Install Complete / job_comp `X` → done grey; **does not** advance zebra index (`bandIndexById` in `JobLogContent.jsx`). Other rows zebra white / blue-100.

Dark done band: `#4b5563` (no print analogue).

### Stage groups (= print)

| Group | Stages (summary) | Fill | Text |
|-------|------------------|------|------|
| FABRICATION | Released … Weld Complete, Hold | `#dbeafe` | `#1e40af` |
| READY_TO_SHIP | Welded QC, Paint*, Store, Ship Planning | `#d1fae5` | `#065f46` |
| COMPLETE | Ship Complete … Complete | `#ede9fe` | `#5b21b6` |

Runtime: `stageGroupColors` in `useJobsFilters.js`; modal pills via `stageTint.js` + `--st-*` tokens.

Stage cell: **full-cell fill** (not a floating pill); label bold, centered.

### Date flags (= print)

| State | Class | Bg | Fg |
|-------|-------|----|----|
| ASAP | `jl-flag-red` | `#ef4444` | `#ffffff` |
| Hard future | `jl-flag-green` | `#22c55e` | `#ffffff` |
| Hard past | `jl-flag-amber` | `#facc15` | `#111827` |

Ship Date **mirrors** Start Install flag logic (keyed off install flags/date, not ship day alone).

### Done-row description links

On `tr.jl-done`, `.text-brand` uses **deeper blue** `#1e3a8a` (not washed opacity on gray-400). Dark mode: `#93c5fd`.

---

## 3. Table lattice & frame

### Critical implementation rule

Use **`border-collapse: separate` + `border-spacing: 0`**.  
`border-collapse: collapse` leaves a **1px white hairline** between cell fills and the outer frame (WebKit/Blink). Do not reintroduce collapse for “cleaner” borders.

### Frame

```text
.job-log-table-frame  →  1px solid var(--grid), border-radius 0.5rem, overflow hidden
.job-log-table        →  separate / spacing 0 / table-layout fixed / width 100%
th/td                 →  border-right + border-bottom (last column: no right border)
thead th              →  bottom border 1.5px (header band anchor)
```

Defined in `tokens.css`. Applied from `JobLogContent.jsx`.

### Hover

```css
tr.jl-row:hover > td:not(.jl-flag) {
  box-shadow: inset 0 0 0 9999px var(--row-hover);
}
```

Does **not** replace cell borders. Flag cells excluded so ASAP/hard dates stay solid.

### Alignment

- Headers and body: **center** by default.
- Header filters: full-width trigger (`ColumnHeaderFilter` `w-full justify-center`).
- Multi-line: Job, Description, Paint color — 2-line clamp, explicit `text-align: center`.
- Stage: full-width button, centered label, no fixed min-width (column % owns width).
- Fab Order input: content-sized (~3.25rem), not full-cell pill.

---

## 4. Column width weights

`COLUMN_WIDTH_PERCENT` in `jobLogColumns.js` (normalized to 100% at render). Tuned ~1280–1700px desktop.

| Column | % | Notes |
|--------|---|--------|
| Job # | 2.7 | |
| Rel | 2.7 | |
| Job Name | **9.3** | |
| Description | **9.3** | Brand link → release hub |
| Fab Hrs | 4.3 | tabular-nums, tight pad |
| Install Hrs | 4.3 | same |
| Paint Color | 5.1 | centered wrap |
| PM | 2.7 | |
| By | 3.1 | |
| Released | 5.2 | |
| Fab Order | 4.4 | compact input; 80.555 |
| Stage | **6.0** | full-cell stage color |
| Ship Date | 5.3 | flag mirror |
| Start Install | 5.8 | flag + installer sub-line |
| Comp ETA | 5.2 | |
| Install Prog | **4.1** | |
| Invoiced | **4.1** | |
| Mats | 3.1 | |
| Notes | **11** | textarea, centered text |
| Actions | 5 | admin gear (when shown) |

Tablet may drop BY + Released and renorm remaining widths.

---

## 5. Page chrome around the table

### Content shell (`ReleasesLayout`)

- Outer: full height minus `--app-chrome-h`, canvas bg, safe-area insets only.
- Inner: `bg-surface`, `p-1.5 gap-1.5` between filter bar and table (no heavy white card).

### Filter toolbar (rail expand/collapse safe)

**Single non-wrapping row**, three zones:

| Zone | Contents | Behavior |
|------|----------|----------|
| Left (shrink-0) | ViewToggle, New, Verbal, Actions, Projects | Fixed |
| Middle (flex-1) | Quick filters | **Horizontal scroll** if tight |
| Right (shrink-0) | Table/Timeline switcher, project-row chevron | Fixed |

- New/Verbal shorten labels under ~1100px.
- Search + stats: one row; stats can scroll; “Last updated” from ~1280px up.
- Thin scrollbars: `.jl-toolbar-scroll` in `index.css`.
- Table scroll: `.job-log-table-scroll` (8px wide thumb).

### Rail

| State | Width | Side pad |
|-------|-------|----------|
| Collapsed | **52px** | 7px |
| Expanded | 212px | 9px |

`frontend/src/components/Rail.jsx` — `RAIL_COLLAPSED` / `RAIL_EXPANDED`.

---

## 6. Print PDF (summary)

| Property | Value |
|----------|-------|
| Page | Tabloid landscape 17″×11″ (1224×792 pt) |
| Margin | 36 pt |
| Fonts | IBM Plex Sans/Mono (or Helvetica/Courier fallback) |
| Zebra / grey / stage / flags | Same RGB as screen tokens above |
| Structure | Per-PM sections; even page pad for duplex |
| Filename | `job-log-review-YYYYMMDD-HHMMSS.pdf` |

---

## 7. Source map (edit here)

| Concern | File |
|---------|------|
| Colors, bands, flags, lattice CSS | `frontend/src/styles/tokens.css` |
| Body type + done-row link blue | `frontend/src/index.css` |
| Tailwind faces + `text-jl*` | `frontend/tailwind.config.js` |
| Column % widths | `frontend/src/utils/jobLogColumns.js` |
| Cell render / stage / dates / fab input | `frontend/src/components/JobsTableRow.jsx` |
| Table frame + header | `frontend/src/pages/JobLogContent.jsx` |
| Toolbar / search / chips | `frontend/src/pages/ReleasesLayout.jsx` |
| Fab order display | `frontend/src/utils/formatters.js` → `formatFabOrder` |
| Stage group palette | `frontend/src/hooks/useJobsFilters.js` |
| Modal stage pills | `frontend/src/utils/stageTint.js` |
| PDF colors + mono set | `frontend/src/utils/jobLogPdf.js` |
| PDF font registration | `frontend/src/utils/pdfFonts.js` |

---

## 8. Non-negotiables (do not regress)

1. **Print RGB** for bands, stage groups, date flags — keep screen tokens matched.
2. **`border-collapse: separate`** for the Job Log table — collapse reintroduces left-edge gap.
3. **IBM Plex** screen + PDF (rebuild TTFs after fontsource bumps).
4. **Mono column set** shared by screen and PDF.
5. **Toolbar:** no `flex-wrap` on the primary control row (scroll the middle strip instead).
6. **80.555** placeholder always three decimals in UI and export.
7. Token changes go in **both** light and `.dark` blocks in `tokens.css`.

---

## 9. Known intentional deltas

| Area | Screen | Print |
|------|--------|-------|
| Type size | ~12.5px body | ~9pt body |
| Header fill | `--head-bg` `#e9edf4` | `#e0e0e0` |
| Grid | Token lattice + separate borders | Darker solid 0.5pt lines |
| Description | Brand link into hub | Plain bold text |
| Dark mode | Full palette | N/A (light only) |
| Handoff `design-tokens.css` | Older band/stage hexes | Superseded by live `tokens.css` |

---

## 10. Restyle checklist

- [ ] Update this pin (or dated successor) after visual changes  
- [ ] Re-export a Review PDF and spot-check bands / stage / ASAP colors  
- [ ] If faces change: fontsource + `index.css` + Tailwind + rebuild `public/fonts`  
- [ ] Keep `MONO_COLUMNS` ↔ row mono rules aligned  
- [ ] After lattice tweaks, verify **no hairline** on first column left edge (Safari + Chrome)  
- [ ] Expand/collapse rail: toolbar height stable, filters scroll not wrap  

---

*End of styling document. Diff future work against this file, not memory or the handoff alone.*
