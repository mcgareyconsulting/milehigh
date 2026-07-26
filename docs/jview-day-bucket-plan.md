# J-View Timeline — Day-Bucket Board Plan

Internal name: **J-View** (there is no separate view — this evolves the existing Timeline at
`/pm-board?view=timeline`, component `frontend/src/components/GanttChart.jsx`).
Parent feature: `docs/feature-plan-2026-06-30.md` §6.

## Locked decisions (2026-07-01)

1. **Layout = day-bucket board.** X-axis is discrete calendar-day columns. Within each
   lane×day cell, cards stack **vertically**, uniform size (Trello-style). A card's column is
   its **date, period** — position never drifts. Column stack height = that day's workload
   (this IS the overload signal; do not "fix" tall days).
2. **Card = point event on `start_install`** (all jobs local → start_install *is* the ship
   date). No span bars in shipping lanes; `comp_eta` is only used for the installer-card
   duration badge. Keep the existing clamp `endDate = max(comp_eta_effective, start_install)`
   (some rows have backward comp_eta).
3. **Zoom changes representation, not just scale.** Range: ~1 week of jumbo cards ↔ ~3-month
   heat map (see zoom table).
4. The **"Enforce dates" toggle, nudge packing, and sub-row packing algorithm are removed** —
   the bucket layout makes them meaningless.
5. Lanes unchanged: `Shipping Planning`, `Shipping Completed` (by DB stage `Ship Planning` /
   `Ship Complete`), then installer roster + off-roster extras. Same `toBar` eligibility rules
   as current code. Each release appears in exactly one lane.

## Layout spec

```
          MON 29     TUE 30     WED 1      THU 2
Ship Pln │[390-533]│          │[440-439]│          │
         │[390-534]│          │          │          │
         │[390-535]│          │          │          │
Ship Cmp │[480-389]│[596-411] │[480-430] │[440-582] │
         │[330-496]│          │          │          │
Saul 1   │[655-1 ▸3d]         │          │[712-4 ▸2d]
```

- **Cell building:** `cells = Map<lane, Map<dayIso, Release[]>>` keyed by
  `dayPart(start_install)`. Pure client selector over `useReleases()` (no new fetches).
- **In-cell sort:** ASAP flag first (`start_install_asap`), then job # asc, then release # asc.
  Deterministic; define once as a comparator constant.
- **Card box:** width = `dayPx - CARD_GUTTER*2`; height fixed per zoom level. Cards stack with
  a small vertical gap; whole stack top-aligned in the lane.
- **Lane height:** `min(maxStackAcrossRange, capForZoom) * (cardH + gap) + chipRow + padding`,
  minimum one card row. One busy day sets the lane's height — acceptable because of the cap.
- **Overflow:** when a cell has more cards than `capForZoom`, render the first `cap-1` plus a
  `+N more` chip. Clicking the chip opens a small popover/modal listing all of that lane+day's
  cards (each clickable → `ReleaseDetailModal`). Keep it dumb: fixed-position panel, click-out
  to close.
- **Duration badge (installer lanes only):** `▸Nd` where
  `N = max(daysBetween(start, endDate)+1, 1)`. Polish (optional, Phase 3): a 3px underline bar
  extending from the card across N day columns to hint crew occupation without span layout.
- **Keep:** hover tooltip, click → `ReleaseDetailModal`, week-snap nav, Today, jump-to-date,
  `filterComplete` behavior, scroll-anchor-on-reflow and anchor-on-zoom effects (all already
  parameterized on `dayPx`).

## Zoom table (starting values — tune by feel)

| Z | Name      | dayPx | ~days @1440w | Cell representation                | Cap | Card detail |
|---|-----------|-------|--------------|-------------------------------------|-----|-------------|
| 0 | Quarter   | 16    | ~80–90       | **Count/heat chip** (no cards): chip shows count, bg intensity scales with count. Click chip → set Z3 + jump to that date. | —   | none |
| 1 | Month     | 42    | ~30          | micro cards, h≈22                   | 3   | `job-rel` |
| 2 | Fortnight | 88    | ~14          | compact cards, h≈40                 | 4   | `job-rel · name` |
| 3 | Week ★    | 180   | ~7 (default) | full cards, h≈64                    | 5   | + description |
| 4 | Focus     | 320   | ~4           | jumbo cards, h≈96                   | 7   | + ship date, crew/stage, PM |

- Reuse the existing progressive-disclosure `CardBody` (min/low/med/high/full ≈ Z1–Z4).
- **Header adapts to dayPx:** ≥60 → weekday+day+month (current); 28–59 → day number only
  (month shown on Mondays/1st); <28 → week tick labels on Mondays ("Jun 29") + month labels.
- Keep the zoom −/+ buttons; keep left-edge date anchoring on zoom change (already built).

## Phases (each independently shippable; run `npx eslint` + `npm run build` in `frontend/` after each)

**Phase 1 — Bucket layout engine. ✅ DONE (2026-07-01).** Replaced the `bands` layout memo with
per-day cells (cards stack vertically in the lane×day cell), removed `enforceDates`/toggle/
`BAR_GAP_PX` nudging, added the per-zoom `cap` + inert `+N more` chip, 5 crude zoom levels
(dayPx 64→300 / cardH 22→98 / cap 4→9), header invariants updated (schema_version 4). Verified
in-browser: every lane 0 box-overlaps, counts preserved (Shipping Completed 17 etc.), 3 same-day
cards stack cleanly.
*Observation that drives Phase 2:* real data is **sparse at day zoom** — Shipping Completed spans
~330 days (historical + future ships scattered), so today's week is often empty and you scroll a
lot. This is correct (the old nudge view only looked full because it packed contiguously). The
far-zoom heat/month view (Z0/Z1) is the fix — prioritize it. Also consider a default landing that
scrolls to the nearest populated day, and/or a time-window filter for stale completed cards.

**Phase 1.1 — natural-height cards + polish. ✅ DONE (2026-07-01).** Per user: (a) zoom now snaps
the left edge to a whole-day boundary (round scaled scrollLeft to dayPx in the zoom anchor effect);
(b) weekly view widened (Z2 dayPx 150→210, ~7 columns) with **no name/description truncation** —
switched in-cell cards from absolute fixed-height to NATURAL document flow (flex-col per cell, text
wraps via `break-words` at wrap zoom levels), and lane heights are now MEASURED post-layout
(useLayoutEffect over `[data-cell]` offsetHeight, guarded against render loops). Zoom presets gained
`minCardH` + `wrap` flags. Verified: 0 clipped wrap elements, 0 cells overflow their lane, zoom
scrollLeft % dayPx === 0. schema_version 5.
*Watch:* far-zoom levels still single-line truncate by design; Phase 2 will replace the far end
with heat chips anyway.

**Phase 1.2 — zoom-to-clean-days + modal tint. ✅ DONE (2026-07-01).** (a) Zoom levels now target a
whole VISIBLE-day count (21/14/7/4/2; default = 1 week) — `dayPx` is derived from the measured
viewport (`ResizeObserver` on the scroll container, `dayPx = (clientWidth - SIDEBAR_PX) / days`), so
exactly N clean columns fill the screen instead of a ragged 6.3. (b) `ReleaseDetailModal` gained an
`accentColor` prop; the card click passes `band.color`, so the modal header matches the lane color
(verified violet=Shipping Completed) instead of the default blue accent gradient. Verified in-browser:
default=7 / out=14,21 / in=4 days; modal header bg === card lane color.

**Phase 1.3 — zoom collapses to week columns. ✅ DONE (2026-07-01).** Generalized the board from
day-only to a `unit: 'day' | 'week'` column model. Zoom order (out→in): 12wk, 6wk, 21d, 14d, 7d★,
4d, 2d — zooming out past the 3-week day view collapses days into WEEK columns (each column = one
week, cards bucket by `floor(daysFromFirst/7)`, headers labelled "WK <Monday>"). `dayPx`→`colPx`,
added `colDays`; all positioning/scroll/snap generalized to columns; zoom re-anchor preserves the
left-edge DATE across day↔week switches (via prev colDays). This front-loads part of Phase 2's
representation switching (heat chips at the very far end still TODO). Verified: clean day→week
transition, 0 overlaps in week mode, whole-column snap. schema_version 6.

**Phase 2 — Zoom range + representation switching.** Implement the zoom table incl. Z0
heat-chip mode and adaptive header. Click-heat-chip → Z3 + jump.
*Verify:* at Z0 a ~3-month span fits on screen; at Z4 cards show all detail lines.

**Phase 3 — Cell affordances.** `+N more` popover with full card list (still inert); in-cell sort
comparator ✅; duration badge (TODO); (optional) occupation underline for installer cards.

**Phase 3.1 — Cover photo thumbnails on cards. ✅ BUILT (2026-07-02), unverified visually (no sandbox
photos).** Trello-card style: at close zoom ("weekly and sooner" = 7/4/2-day levels, `imgH` 66/96/128)
a card shows its cover photo (manifest/cover-sheet) as a thumbnail above the text, with a `📎 N`
count badge. Cover = the release's NEWEST non-deleted `ReleasePhoto` (v1 heuristic). Backend: batched
`_release_cover_photos()` in job_log/routes.py (mirrors `_release_ids_with_drawings`), patched into
BOTH serializers (`/brain/jobs` + `/brain/get-all-jobs`) → emits `cover_photo_id` + `photo_count`;
verified present in the API response. Frontend: `<img>` from `/brain/releases/{id}/photos/{coverId}/file`
(same URL pattern ReleaseDetailModal uses). NOT visually confirmed — sandbox has 0 release photos.
Cover heuristic (user-confirmed 2026-07-02): the manifest routes through the EXISTING photo upload
(`POST /brain/releases/<id>/photos` → `ReleasePhoto`) — no separate path. Cover = "most recent photo
once in the shipping stage", which in practice = the release's newest photo (shipping is the last
thing photographed), so the current newest-photo rule already surfaces the manifest. Robustness
refinement (cheap, available now): prefer the newest photo whose `ReleasePhoto.stage` is a shipping
stage, fall back to newest overall — guards against a later non-manifest upload stealing the cover.
FUTURE ("scan for the manifest"): actively detect the cover-sheet photo (OCR / filename-note hint like
"manifest"/"worksheet"/"shipped" / aspect ratio) and prioritize it. Integration idea: the 5b
"mark shipped" drag could open the existing photo uploader so Jay adds the manifest at completion,
which then auto-becomes the cover.

**Phase 5 — Drag interactions. ✅ v1 BUILT (2026-07-02), write path untested live.** Native HTML5 DnD
in GanttChart. (5a) installer-lane card dragged to another DAY column → `updateStartInstall`; (5b)
Shipping Planning card dragged into Shipping Completed → `updateStage('Ship Complete')`, one-way.
Optimistic `overrides` state (card jumps immediately), reconciled against the poll, reverted on error;
drop-target lane highlight; `refetch()` on success. Installer-to-installer moves NOT handled. The
photo-prompt-on-complete and reverse-drag questions remain OPEN (deferred). NOT tested end-to-end
because a real drop writes to the sandbox DB (stage/date change on a live release) — pending a live
test with user okay.

**Phase 4 — Polish.** Weekend handling const (render dimmed vs collapse Sat/Sun — decide by
feel), memoization pass, empty-lane collapse option.

**Phase 5 — Drag interactions (separate slice, do NOT bundle).** Native HTML5 DnD (matches
DWL's `useDWLDragAndDrop` pattern; dnd-kit only if needed). Drop target = lane×column cell
(the grid gives these for free). Drag MEANING depends on lane type — two distinct behaviors:

- **5a. Installer lanes — horizontal date drag.** Drop a card in a different day/week column →
  reschedule `start_install`. Calls the same endpoint `StartInstallDateModal` uses,
  `/brain/update-start-install/<job>/<release>` → `UpdateStartInstallCommand` (recomputes
  comp_eta, events/undo, Trello outbox). Optimistic UI; the 30s `ReleasesContext` poll reconciles.
- **5b. Shipping lanes — vertical stage drag (Jay's flow).** Probably NO horizontal (date) drag
  here. Instead Jay slides a card from **Shipping Planning → Shipping Completed**, which is a STAGE
  change (`Ship Planning` → `Ship Complete`) via `PATCH /brain/update-stage/<job>/<release>` →
  `UpdateStageCommand` (already handles Trello move, ASAP-drop cascade, events/undo). The card keeps
  its date column — only the lane/stage changes. Mirrors the original §6 flow: "works only in the
  list, adds photos, moves to Shipping Complete."
  - OPEN: does completion prompt/require a **photo** on drop (Jay's documented flow adds photos
    before completing) or just flip the stage? — pending user decision.
  - OPEN: is the reverse drag (Completed → Planning) allowed (undo), or one-way?
  - Note: Ship Complete does NOT neutralize the install date or touch job_comp (only Complete/
    Install Complete do); ASAP is dropped. So the stage flip is comparatively clean.

**Backlog / later slices:**
- **Departure board panel** — big-type "TODAY / THIS WEEK" ship list beside/above the board;
  the shipping guy's 80% glance.
- **Unscheduled parking column** — releases in Ship Planning without a hard date, pinned left;
  drag onto a day to schedule (pairs with Phase 5).
- **Department × day matrix** — long-term goal (schedule releases per department). Needs a
  data-model addition (planned per-department windows; today only stage *actuals* exist via
  `ReleaseEvents`). Cell capacity tint = Σ card hours vs department capacity. Backend design
  required first — do not attempt from the frontend.

## Regression probe (run in browser console on the Timeline)

```js
[...document.querySelectorAll('[data-lane]')].map(l => {
  const cards = [...l.children[1].querySelectorAll('div.absolute.rounded.shadow-sm')]
    .map(c => ({ l: parseFloat(c.style.left), r: parseFloat(c.style.left)+parseFloat(c.style.width), t: parseFloat(c.style.top) }));
  let overlaps = 0;
  for (let i=0;i<cards.length;i++) for (let j=i+1;j<cards.length;j++) {
    const a=cards[i], b=cards[j];
    if (Math.abs(a.t-b.t)<1 && a.l<b.r-0.5 && b.l<a.r-0.5) overlaps++;
  }
  return { lane: l.getAttribute('data-lane'), count: cards.length, overlaps };
}).filter(x => x.count);
```
Every lane must report `overlaps: 0`, and counts must not drop when changing zoom (cap overflow
goes to the `+N` chip, never silently hidden).
