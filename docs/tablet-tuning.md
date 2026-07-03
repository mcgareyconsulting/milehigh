# Tablet Tuning Tracker

Cross-application iPad/tablet-view tuning, run in tandem with the `feature/jay-view`
timeline work. Client released a physical iPad to Daniel's desk for on-device verification.

**How to use this doc:** issues are triaged into three states —
`[ ]` open · `[~]` in progress · `[x]` fixed. Each item notes the file(s), the failure
mode, and the fix approach. "Confirmed on device" = reproduced on the physical iPad;
"static" = found by code sweep, still needs device confirmation.

Test target: iPad Safari (touch). Also sanity-check iPad landscape vs portrait.

## View matrix (Job Log) — shared vocabulary for reporting issues

Five distinct view×breakpoint combos exist. `useBreakpoint()` (`hooks/useBreakpoint.js`)
buckets width into isMobile(<768) / isTablet(768–1279) / isDesktop(≥1280). `ReleasesLayout`
combines that with the user's `ViewToggle` pick (Table / Cards / **Auto**, top-left of the
Job Log toolbar, persisted as `jl_view`) into `effectiveView`:

| Name | Breakpoint | ViewToggle | Renders |
|---|---|---|---|
| **Laptop Table** | ≥1280px | any | `JobsTableRow` full table, `showAdminActions` (⚙) visible |
| **Landscape-Tablet Table** | 768–1279 | **Table** (explicit) | `JobsTableRow`, Banana Code/BY/Released columns dropped, ⚙ hidden |
| **Landscape-Tablet Cards** | 768–1279 | Auto (default) or **Cards** | `JobLogRow` dense expandable rows (`JobLogRowList`) |
| **Portrait-Tablet Cards** | 768–1279, narrow | same as above | same component, just less horizontal room |
| **Phone Tiles** | <768 | any (Auto/Cards force mobilecard) | `JobLogCardGrid` |

**Key nuance:** in **Auto** mode (the default), tablet-width always gets Cards — Table view
only appears on tablet if the user explicitly selects it via the ViewToggle. Both Table and
Cards are reachable on landscape tablet via that toggle, which is the intended UX per Daniel's
2026-07-03 note: tune both, not just one.

**Reporting convention:** name the view from this table (e.g. "in Landscape-Tablet Table, ⚙
column..." or "in Landscape-Tablet Cards, the Stage pill...") so there's no re-discovery per
issue. Screenshots from the physical iPad (or Daniel's Chrome via claude-in-chrome) resolve
ambiguous visual issues (alignment, color, spacing) far faster than describing them in text —
prefer a screenshot over a paragraph when something looks "off" visually.

**Workflow note (2026-07-03):** for pure Tailwind/layout/color tweaks, skip the
lint+compile-check ceremony per edit — batch several tweaks, apply them together, and let the
user eyeball the live hot-reload result. Save verification rigor for logic changes (cascades,
data model, migrations). Session switched to Sonnet 5 for this fast-iteration phase.

## Running the branch on the iPad (device mode)

Live hot-reload testing on a tablet over the LAN. iPad and Mac must be on the same Wi-Fi.

1. Backend (unchanged): `python run.py`  → Flask on localhost:8000
2. Frontend, device mode: `cd frontend && npm run dev:ipad`
3. iPad Safari → `http://<mac-lan-ip>:5173`  (Daniel's Mac was `172.16.4.27` on 2026-07-03;
   re-check with `ipconfig getifaddr en0` since DHCP can reassign it)

How it works: `dev:ipad` = `VITE_PROXY_API=1 vite --host`. `--host` exposes Vite on the LAN;
`VITE_PROXY_API=1` flips the frontend to same-origin URLs (`api.js`) so API calls hit Vite,
which proxies `/api /brain /admin /procore /trello /lake` to Flask (`vite.config.js`,
`deviceProxy`). Same-origin ⇒ no CORS, session cookies work. The proxy is SPA-aware: real page
navigations fall through to Vite (so client routes like `/admin/fc-collection` still load),
only XHR/fetch is proxied. Normal `npm run dev` is completely unchanged.

If the LAN IP can't be reached (public/coffee-shop Wi-Fi enforces AP client-isolation — the
common case), use **Tailscale** instead: it's installed on the Mac (`Tailscale.app`) and the
iPad (`ipad157`), both on the `mcgareyconsulting@` tailnet. The Mac's tailnet IP is
**`100.116.150.76`** (stable per-device), so the iPad opens **`http://100.116.150.76:5173`**
regardless of the network. No config change needed — device mode is same-origin, so API calls
proxy correctly over the tunnel too. This also lets Jay test remotely. CLI:
`/Applications/Tailscale.app/Contents/MacOS/Tailscale status`.

---

## A. Systemic issues (affect many pages — fix once, benefit everywhere)

### A1. Native HTML5 drag-and-drop is dead on iPad  🚩 highest impact
`draggable` + `onDragStart`/`onDragOver`/`onDrop` do not fire on iOS Safari touch. Every
drag interaction below silently does nothing on the tablet.

**Be surgical about which surfaces get a touch-drag replacement — do NOT add drag where it
doesn't exist today.** Notably **Job Log has no active drag reorder** and must stay that way:
`JobsTableRow.jsx:69` hardcodes `isDraggable = false`, and `JobLogContent.jsx:96,99` wire
empty no-op `handleDragStart`/`handleDrop`. Those `onDragStart` hits are dead wiring — leave
them, don't revive them into a touch gesture.

Surfaces with genuinely ACTIVE native drag (these are the fix candidates):
- `components/GanttChart.jsx` — timeline stage-change (Ship Planning → Ship Complete)
- `components/PMBoardList.jsx` — PM board card moves
- `components/TableRow.jsx` (Drafting Work Load row) — title-cell reorder, admin + single-assignee only (`isDraggable = isAdmin && !hasMultipleAssignees`)
- `pages/Archive.jsx` — archive drag (verify active)
- `pages/Board.jsx` + `components/board/NewItemModal.jsx`, `components/board/BoardPhotos.jsx` — file/photo drop zones (native drop is fine on desktop; touch needs a tap-to-upload path)

Dead / disabled wiring — do not touch:
- `pages/JobLogContent.jsx`, `components/JobsTableRow.jsx` — Job Log reorder is disabled; no drag on device is correct behavior.

Fix options (decide per surface):
- **dnd-kit + TouchSensor** — keep the drag gesture, make it touch-native. Board.jsx already
  depends on dnd-kit, so it's in the bundle. Best where drag is the natural mental model
  (Kanban, timeline lanes).
- **Tap-based fallback** — tap card → action sheet ("Move to Ship Complete", "Reorder…").
  Often better than drag on a tablet; simpler for row lists.
- [ ] Decide the standard pattern, then convert surface-by-surface.

### A2. dnd-kit uses PointerSensor with no touch tuning
`pages/Board.jsx:189` — `useSensor(PointerSensor, { activationConstraint: { distance: 8 } })`.
PointerSensor fires on touch but can fight page scroll and has no press-delay. On device,
verify drag vs scroll doesn't conflict; likely wants a `TouchSensor` with a short delay or
`touch-action` on the handle.
- [ ] Verify Board drag on device; add TouchSensor if it fights scroll.

### A3. `title=` tooltips never appear on touch
Many components rely on `title=` for hover tooltips (TableRow ×16, PdfMarkupModal ×10,
ReleasesLayout ×8, JobsTableRow ×8, DraftingWorkLoad ×7…). On iPad these information
affordances are invisible. Audit which carry *essential* info (vs. redundant) and give those
a tap-reveal or always-visible treatment.
- [ ] Triage title= usages: essential vs decorative.

### A4. Hover-only affordances
`group-hover:` / `hover:opacity` / `hover:visible` used as the *sole* trigger to reveal
controls in: BoardPhotos, NewItemModal, EventsList, GanttChart, JobLogCard, JobsTableRow,
PMBoardCardModal, SubmittalCard, Dashboard. Anything revealed only on hover is unreachable on
touch — must have an always-visible or tap state.
- [ ] Audit hover-reveal controls for a touch trigger.

### A5. Touch target sizing
Zoom/nav buttons, `+N more` chips, filter chips, icon buttons — confirm ≥44×44px hit areas
(iOS HIG). Small controls are the #1 "feels bad on tablet" complaint.
- [ ] Sweep for sub-44px interactive elements.

### A6. Viewport / Safari chrome
`index.html` viewport is `width=device-width, initial-scale=1.0`. Consider `viewport-fit=cover`
and confirm Safari's dynamic bottom toolbar doesn't clip the last lane/row.
- [ ] Device-check bottom-of-screen clipping.

---

## B. Per-page issues

### Timeline / J-View (`GanttChart.jsx`)
- [ ] A1 stage-change drag (see above) — the just-shipped feature is inert on iPad.
- [ ] Horizontal day-scroll momentum + vertical scroll interplay — verify on device.
- [ ] `+N more` chip tap target + popover click-out on touch.

### PM Board (`PMBoardList.jsx`)
- [ ] A1 card-move drag inert on iPad.

### Job Log (`JobLogContent.jsx`, `JobsTableRow.jsx`)
- No drag reorder exists (disabled by design) — do NOT add one. Nothing to fix re: A1.
- [x] Hide the Banana Code (Urgency) column at tablet width (`NARROW_HIDDEN`, gated on `!isDesktop`).
- [x] Admin row-actions ⚙ column (edit/delete) is desktop-only (14"+): `showAdminActions =
  isAdmin && isDesktop` gates the header `<th>`, the per-row `showActions`, and the colSpan
  math. Cards view (`JobLogRow`) already embedded `JobsTableRow` with `showActions={false}`, so
  it was never exposed there; `JobLogCardGrid` passes no `isAdmin`. Admin cell-editing on tablet
  is intentionally preserved — only the gear/delete tool is hidden.
- [ ] Wide table horizontal-scroll behavior on tablet width.
- [x] **Landscape-Tablet Table, 2026-07-03:** header vertical/bottom dividers switched from
  `border-collapse`-based borders to absolutely-positioned bars (`<span className="absolute
  ...">`) — Safari (iPad) has a known bug where collapsed borders on `position: sticky` cells
  can fail to paint, even though the same code renders fine in desktop Chrome. Applies to both
  the main `<th>` loop and the ⚙ header cell in `JobLogContent.jsx`.
- [x] **Invoiced / Job Comp inputs drifting right on tablet:** both had a hardcoded
  `style={{ minWidth: '48px' }}` in `JobsTableRow.jsx` that overflows once the tablet column
  redistribution shrinks that column below 48px — the input's floor forces it wider than its
  `<td>`, spilling right. Removed the inline style, added `min-w-0` so `w-full` actually shrinks
  to fit (Tailwind's border-box preflight makes this safe). Fixes Cards view too since
  `JobLogRow`'s expanded section embeds the same `JobsTableRow`.
- [x] **Fab Hrs / Install HRS values drifting/not centered on tablet:** those columns carried
  the thinnest weight tier (3) in `COLUMN_WIDTH_PERCENT`, too tight for 6-char values like
  `151.40` once other columns claimed their share — `whitespace-nowrap` text overflowed the
  cell. Bumped Fab Hrs/Install HRS 3→3.5, Job Comp/Invoiced 4→4.5 (extra margin beyond the input
  fix above), funded by trimming Notes 9→8.
- Note: browser-resize emulation (claude-in-chrome `resize_window`) did not reliably shrink the
  viewport below laptop width in this session (screenshots stayed at native ~1512px width
  regardless of requested size) — root causes above were diagnosed from code, not visually
  reproduced. Verify on the physical iPad and report back if drift/centering persists.
- [ ] **Attempted fix, reverted (2026-07-03):** user reported a thin gray sliver from the
  "Complete" row's background peeking through right under the sticky header (classic sticky+
  sub-pixel seam). Tried (a) solid `bg-gray-100 dark:bg-slate-700` on the `<thead>` itself and
  (b) extending the bottom-divider bar past its own edge (`-bottom-px h-[3px]`) to mask any gap
  — user reported this looked WORSE, reverted both back to the known-good baseline (plain
  `<thead className="sticky top-0 z-10">`, divider bar `bottom-0 h-0.5`). Root cause of the
  original sliver is still open; next attempt should get a screenshot of the *current* (reverted)
  state first, since this was diagnosed blind (browser resize tool not cooperating this
  session) and the guess made it worse rather than better.
- [x] **Body cell dividers invisible on gray "Complete" rows (2026-07-03, confirmed via
  screenshot, both light+dark):** the default divider color (`border-gray-300
  dark:border-slate-600`) has almost no contrast against the gray "Complete"/invoice-comp row
  background (`bg-gray-400` light / `bg-slate-500` dark) — the two screenshots showed a flat gray
  slab with zero visible column separation on those rows. Fix in `JobsTableRow.jsx`: added
  `cellDividerClass = isGrayed ? 'border-gray-600 dark:border-slate-700' : 'border-gray-300
  dark:border-slate-600'` next to `rowBgClass`, and replaced all 11 static
  `border-r border-gray-300 dark:border-slate-600` occurrences with `border-r
  ${cellDividerClass}`. Normal (white/blue) rows keep the original color; gray rows get a
  darker, higher-contrast one in both themes. Also thickened the header's vertical divider
  span `w-px → w-0.5` for a crisper "cell divider" look per the same feedback. Cards view
  (`JobLogRow`'s expanded section) inherits this for free since it embeds `JobsTableRow`.
- [x] **Coherence redesign (2026-07-03, decided via 4-question clarifier):** the table read as
  "4–5 styles frankensteined" because (a) the divider ink changed color per surface (header
  gray-500, normal rows gray-300, gray rows gray-500/600), (b) five competing background tones,
  (c) dark mode had an INVERTED hierarchy — complete rows (slate-500) glowed brighter than
  active rows, and the header bg (slate-700) was identical to alt rows. Decisions: **one
  translucent divider ink everywhere** (black 18% light / white 12% dark, box-shadow verticals +
  `border-black/[0.18] dark:border-white/[0.12]` horizontals; header bottom rule is the same ink
  at ~2× alpha `#0000005c`/`#ffffff3d` — keep JobsTableRow + JobLogContent in sync);
  **complete rows muted + receding** (`bg-gray-200 dark:bg-slate-900`, content dimmed via
  `tr.jl-done` CSS rule in `index.css` — specificity (0,1,2) out-guns Tailwind text utilities,
  inline-styled elements like the Stage pill keep their colors; editor inputs soften to
  translucent bg); **alt rows stay bold blue-300**; **dark header goes slate-900 band** +
  `tracking-wide` labels. Cards view (`JobLogRow`) synced: same muted slab, blue-200→300 to
  match the table, primary text dims when complete.

### Drafting Work Load (`DraftingWorkLoad.jsx` / `TableRow.jsx`)
- [ ] A1 title-cell reorder drag (admin + single-assignee) inert on iPad.

### Board / bug tracker (`Board.jsx`)
- [ ] A2 verify dnd-kit drag on touch.
- [ ] Photo/file drop → needs tap-to-upload on touch (A1).

### Tables generally (Archive, History, InvoicingReport, Logs, Operations, RentalReports, JobSearch, FcCollection)
- [ ] Confirm `overflow-x` containers scroll cleanly on tablet and don't break page layout.

---

## C. Device-reported issues (fill in from the physical iPad)

_Log what you see on the tablet here as you walk each page. Format:_
_`[ ] <page> — <what's wrong> — (portrait/landscape)`_

- [ ]
