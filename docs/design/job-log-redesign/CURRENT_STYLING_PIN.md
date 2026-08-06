# Job Log — current styling pin

**Pinned:** 2026-08-06  
**Purpose:** Snapshot of how the live Job Log *and* the print PDF look *now*, before further restyling. Use this as the baseline; do not treat the Aug 2026 design handoff alone as “what shipped.”

**Reference PDF inspected:** `~/Downloads/job-log-review-20260806-125236.pdf`  
**Related handoff (intent):** `docs/design/job-log-redesign/README.md` + `design-tokens.css`  
**Live tokens (shipped):** `frontend/src/styles/tokens.css`  
**Print builder:** `frontend/src/utils/jobLogPdf.js` + `frontend/src/utils/pdfFonts.js`

---

## 1. Typography (verified against print PDF)

### Faces

| Role | Face | Where it comes from |
|------|------|---------------------|
| UI / free text | **IBM Plex Sans** | `@fontsource/ibm-plex-sans` → `index.css`; Tailwind `font-sans` |
| Numbers, dates, ids | **IBM Plex Mono** | `@fontsource/ibm-plex-mono` → `index.css`; Tailwind `font-mono` |
| PDF embed | Same families, TTFs in `frontend/public/fonts/` | Built from fontsource WOFFs by `scripts/build_pdf_fonts.py` |
| PDF fallback | Helvetica / Courier | Only if TTF fetch/register fails (`pdfFonts.js`) |

**PDF file check (2026-08-06 sample):** `/BaseFont` counts show active **IBMPlexSans** (4) and **IBMPlexMono** (4). Single Helvetica/Courier/Times/Symbol entries are jsPDF’s standard-14 catalog, not the table body.

jsPDF family names (no spaces): `IBMPlexSans`, `IBMPlexMono`. CSS family names: `"IBM Plex Sans"`, `"IBM Plex Mono"`.

### Weights loaded (screen)

- Sans: 400, 500, 600, 700  
- Mono: 400, 500, 600, 700  

PDF only embeds **400 + 700** of each (regular + bold).

### Type scale (Job Log table — Tailwind tokens)

| Token | Size | Typical use |
|-------|------|-------------|
| `text-jl` | 12.5px / 1.2 | Body cells |
| `text-jl-compact` | 12px / 1.2 | Compact density |
| `text-jl-2` | 11.5px / 1.2 | Secondary (Job name, PM, BY, Paint) |
| `text-jl-3` | 10.5px / 1.15 | Sub-lines (e.g. installer under Start install) |
| `text-jl-head` | 12px / 1.15 | Column headers |
| `text-jl-label` | 11px / 1.2 + `.06em` tracking | Section labels (modal) |

Old Man Mode bumps many sizes via `html.old-man` overrides in `index.css`.

### Print PDF type (not identical pt sizes)

| Surface | Size |
|---------|------|
| Body | 9 pt |
| Header | 9.5 pt bold |
| Line height ratio | 1.15 |
| Cell pad | 1.5 pt V / 3 pt H |
| Max lines / cell | 2 (ellipsis) |

Screen aims at the handoff scale (~12.5px); print is denser for tabloid landscape.

### Mono vs sans column split

**Mono (screen + PDF):** Job #, Release #, Fab Hrs, Install HRS, Released, Fab Order, Ship Date, Start install, Comp. ETA, Job Comp, Invoiced.

**Sans:** Job, Description, Stage, Notes, Paint color, PM, BY, Urgency (icons), header row, Mat. Ord.

Implementation: `JobsTableRow.jsx` (`cellMono` / special cases); PDF `MONO_COLUMNS` in `jobLogPdf.js` (must stay in sync).

---

## 2. Color tokens (live)

Applied via `frontend/src/styles/tokens.css` on `:root` / `.dark` (class on `<html>`, not handoff’s `data-theme`).

### Light (summary)

| Token | Value | Role |
|-------|-------|------|
| `--bg` | `#eef1f6` | App canvas |
| `--surface` | `#ffffff` | Surface / band A |
| `--surface-2` | `#f7f9fc` | Raised surface |
| `--head-bg` | `#e9edf4` | Table header |
| `--grid` | `#b6bfcd` | Table lattice |
| `--text` / `--text-2` / `--text-3` | `#0a0a0a` / `#1f2937` / `#4b5563` | Near-black primary (= PDF black); darker secondary/tertiary |
| `--accent` | `#2f5fd0` | Brand / links |
| `--band-b` | `#dbeafe` | Zebra B (= PDF blue-100) |
| `--band-done` | `#9ca3af` | Complete grey (= PDF gray-400) |
| `--row-hover` | `rgba(30,90,200,.07)` | Hover overlay |
| Stage blue/green/purple | `#dbeafe`/`#1e40af`, `#d1fae5`/`#065f46`, `#ede9fe`/`#5b21b6` | = PDF STAGE_GROUP_COLORS |
| Flag ASAP / hard future / hard past | `#ef4444`+white / `#22c55e`+white / `#facc15`+`#111827` | = PDF red-500 / green-500 / yellow-400 |
| `--rail-bg` | `#16203a` | Left rail |

Dark palette is the `.dark` block in the same file. Tailwind maps: `bg-surface`, `bg-head-bg`, `border-grid`, `text-ink`, `text-brand`, etc. (`tailwind.config.js`).

### Row band classes

| Class | Meaning |
|-------|---------|
| `jl-band-a` | Zebra even (active rows) |
| `jl-band-b` | Zebra odd |
| `jl-band-done` | Complete / job_comp X |
| `jl-flag-red` / `green` / `amber` | Full-cell date flags |

Banding rule: Install Complete (and job_comp `X`) rows are grey and **do not** advance the zebra index (`bandIndexById` in `JobLogContent.jsx`).

### Print-only RGB (partial — PDF does not use CSS vars)

| Use | RGB |
|-----|-----|
| Even row | `219, 234, 254` |
| Grayed | `156, 163, 175` |
| Head fill | `224, 224, 224` |
| ASAP / hard future / hard past | red-500 / green-500 / yellow-400 Tailwind-ish |
| Stage groups | FAB blue, READY green, COMPLETE purple fills |

Print grid ink is darker (`40,40,40`) than screen `--grid`.

---

## 3. Table geometry (live)

| Property | Current |
|----------|---------|
| Layout | `table-layout: fixed`, `border-collapse: collapse`, full width |
| Grid | 1px via `box-shadow: inset -1px 0 0 0 var(--grid)` on cells (not `border` under collapse) |
| Header | Sticky, `bg-head-bg`, bold, centered, `text-jl-head` |
| Alignment | Center for essentially all body cells |
| Body text | `text-jl` (12.5px) default; secondary `text-jl-2` |
| Padding | `py-0.5` body, `py-2` header (Old Man: `py-2` body) |
| Description | Semibold brand (`text-brand`) link → release hub |
| Job name | Secondary ink, 2-line clamp, no link |
| Release # | Mono semibold, plain text |
| Row click | Description (and some cells) open hub; not full-row click everywhere |

Column widths: percent map from layout / `columnWidthPercents` (see job log column utils). Tablet drops BY + Released and renorms widths.

---

## 4. Chrome around the table

| Piece | Notes |
|-------|-------|
| Shell | App shell row: left rail + content (`AppShell.jsx`) |
| Rail | Dark navy, icons; expanded label uses Plex |
| Page fill | `calc(100vh - var(--app-chrome-h))` pattern |
| Filters / toolbar | ReleasesLayout — chips, search, view switcher, PDF export |
| Density | Table / cards / mobile cards via breakpoint + view toggle |

---

## 5. PDF export geometry

| Property | Value |
|----------|-------|
| Page | Tabloid landscape 17″ × 11″ (1224 × 792 pt) |
| Margin | 36 pt |
| Theme | jspdf-autotable `grid` |
| Structure | One PM block per section; each PM starts on a new page; non-final PMs padded to even page count for duplex |
| Urgency | Rasterized Banana Code icon strip (not live SVG in PDF) |
| Filename pattern | `job-log-review-YYYYMMDD-HHMMSS.pdf` |

---

## 6. Source map (edit here)

| Concern | File |
|---------|------|
| Screen fonts + base body | `frontend/src/index.css` |
| Design tokens / bands / flags | `frontend/src/styles/tokens.css` |
| Tailwind faces + `text-jl*` | `frontend/tailwind.config.js` |
| Table body cells | `frontend/src/components/JobsTableRow.jsx` |
| Table header / shell | `frontend/src/pages/JobLogContent.jsx` |
| PDF layout | `frontend/src/utils/jobLogPdf.js` |
| PDF font registration | `frontend/src/utils/pdfFonts.js` |
| TTF rebuild | `scripts/build_pdf_fonts.py` → `frontend/public/fonts/` |
| Design intent (pre-ship) | `docs/design/job-log-redesign/README.md` |

---

## 7. Known deltas (screen vs print vs handoff)

These are intentional or residual differences worth not “fixing” blindly:

1. **Print pt vs screen px** — denser on paper; same type *family*, not same *size*.
2. **Print head fill** `#e0e0e0` vs screen `--head-bg` `#e9edf4`.
3. **Print grid** darker solid lines vs screen token lattice + inset shadows.
4. **Description** — handoff: bold dark full-row click; live: brand link (only hub entry).
5. **Row bands + stage fills (2026-08-06)** — light-mode live tokens match PDF RGB for zebra B, grayed rows, and stage groups. Dark mode has no print analogue; done rows use mid slate `#4b5563`.
6. **Notes** — PDF treats as sans free text; generic screen branch may still apply mono to residual columns — keep `MONO_COLUMNS` and `JobsTableRow` special-cases aligned when restyling.
7. **Handoff tokens** in `design-tokens.css` still list older band/stage hexes; live `tokens.css` is the print-aligned set.

---

## 8. Restyling checklist (when you change look)

- [ ] Update this pin (or add a dated successor) so “current” stays true  
- [ ] Keep PDF + screen **family** match (Plex) unless product decides otherwise  
- [ ] If faces change: update `@fontsource/*`, `index.css`, Tailwind, rebuild TTFs, re-export a sample PDF and re-check `/BaseFont`  
- [ ] Keep `MONO_COLUMNS` ↔ `JobsTableRow` mono rules in lockstep  
- [ ] Token changes go in `tokens.css` **both** light and `.dark` blocks  

---

*End of pin. Next styling work should diff against this document, not against memory.*
