# Release Modal — Mobile Recommendations

Companion to the "Subs Mobile View Redesign" canvas (row 3: Release · Details, Attachments, Drawing viewer, Viewer sheet, Activity). Same tokens as the Option A spec (`--ind #2f3f8f`, `--bg #eef0f5`, `--ink #151b33`, `--muted #5b6478`, `--line #d9dde8`, Lato).

## 1. The modal becomes a page

On desktop the release is a modal over the Job Log. On a phone there is no room for that, and the modal's own chrome (title block, tabs, right-hand activity rail) eats the screen. Make it a route:

- `/releases/:id` pushed from the Job Log card; back arrow returns to the log with scroll position preserved.
- Header, two rows:
  - **Row 1 (52px):** back · `480-928.1` number chip · **stage chip** (tappable — opens the stage picker so a stage change is still one tap from anywhere) · `⋯`
  - **Row 2:** job name (17px/900), then `release name · PM GA · Detailed by CBA` (14px muted), both single-line ellipsized.
- `⋯` menu holds what was header clutter on desktop: Open in Procore, Open in Trello, Copy link, Close.
- Sub avatars (the banana row) are dropped from the mobile header; they surface on the Splices tab where they mean something.

## 2. Tabs: horizontal strip, ordered by field use

```
Details | Attachments 2 | Activity 6 | Issues | Splices 1 | Change Log →
```

- 44px tall, `overflow-x: auto`, no scrollbar, active tab has a 2px indigo underline. Counts as small badges.
- Order is by what a sub actually touches, not the desktop order. Details, Attachments and Activity are always visible; the rest scroll in from the right.
- Keep the strip sticky under the header so switching tabs never requires scrolling back up.

## 3. Details tab

The three desktop columns (photos+materials, schedule+details, activity) collapse to one scroll in this order:

1. **Action pair** at the top: `Take photo` and `Add note` — the two things a field crew does most. 44px, side by side.
2. **Photos** as a horizontal strip (220×150 thumbnails, caption `Sep 21 · Gary Almeida · Released`) with a dashed "Upload" tile at the end. "See all" opens the Attachments tab.
3. **Schedule** as key/value rows. Read-only dates are bold text; Install prog is a number field.
4. **Details** as key/value rows. Editable fields render as real controls (Stage, Installer, Billing tag = select; Crew = number). Read-only ones (Install hrs, Fab order, Paint) are plain bold.
5. Materials and To-dos move below the fold; when empty, show one muted line rather than a section header.

Row spec: `min-height:44px`, label 15px ink, value 15px/700, 1px `--line` divider. Section labels 12px/800 uppercase, muted, 0.8px tracking.

## 4. Attachments — reader, not editor

The desktop viewer is a **markup editor**: pen/text/shape tools, color palette, undo, version selector, Carmen review pane, comments, info. That's what makes it feel impossible on a phone. The fix is to stop trying to ship the editor and ship a **reader** with two narrow authoring actions.

### 4a. Attachments tab (list)

- **Drawings** section: one row per file — PDF icon, filename, `2 pages · 173 KB · Bill O'Neill, Sep 21`, chips for `v2 · current` and `6 markups`. Header action: `Pull from Procore`.
- Older versions live behind the row's `⋯` (no version dropdown in the list).
- **Photos** section: same row shape, image icon, `at Released` stage tag.
- **Review** section: Carmen status chip (`Not run` / `Passed` / `3 findings`). Findings summary in one line; tapping opens the viewer's Carmen sheet.
- Sticky bottom bar: `Take photo` (primary) and `Upload file` (secondary), 48px.

### 4b. Drawing viewer

- Full-screen, dark ground (`#4b5162`), page rendered at fit-width, **pinch-zoom + pan** (use the PDF renderer's native canvas, not an `<iframe>`).
- Header: back · filename · `v2 · page 1 of 2 · 480-928.1` · Open in Procore · `⋯` (download, share, other versions).
- **Existing markups render as numbered pins** at the markup's bounding-box origin, colored by author type (red = detailer/PM, indigo = QC). The actual vector markups still draw on the page; pins are the tap target since a 1px stroke is not tappable.
- Floating right-side buttons: zoom-to-fit, markups on/off.
- Bottom bar, four buttons only, 48px each:
  - `1 / 2` — page stepper (tap for a page picker on longer sets)
  - `Drop pin` — the only authoring: tap a spot, type a note, optional photo. Stored as a markup of type `pin` so it appears in the desktop Markups list.
  - `Photo` — attaches a photo to this drawing/page (shows in Photos and Activity).
  - `Carmen` — opens the sheet on the Carmen tab.
- Hint pill on first open: "Pinch to zoom · tap a pin to read it".

### 4c. Viewer sheet (tap a pin, or Carmen)

- Bottom sheet, ~560px, drag handle, three tabs: **Markups** (count) · Comments · Carmen.
- Markups tab: list of numbered rows — pin number, author, date, text. Tapping a row zooms the page to that markup. Extra pages summarized ("3 more on page 2").
- Footer: `Reply` and `Ask Carmen` (48px).
- Carmen tab: findings from the last run (read-only) plus the quick-question chips (`Summarize this drawing set`, `What changed in the markups on this version?`). Running the full code-compliance review stays a desktop action; say so in the empty state.

### What stays desktop-only

Pen / text / shape / arrow tools, color palette, undo/redo, deleting markups, version-to-version compare, running a full Carmen review, page thumbnails/reorder. If a sub really needs to draw in the field, the most I'd add is a single freehand pen in one color, behind a "Mark up" button — not the toolbar.

## 5. Activity tab

- The desktop right-hand rail becomes a tab. Same rows: day dividers, avatar initials, `before → after` chips for stage and fab-order changes, plain text for photo/drawing events.
- **Note composer pinned to the bottom** (`Add a note…` + camera button), above the safe area. Notes and photos are the main thing subs contribute from the field, so it should never be more than one tap away.
- Default newest-first; no "oldest first" toggle on mobile.

## 6. Interaction notes

- All controls ≥44px. Header buttons are 44×44 with the icon centered.
- Stage picker is a bottom sheet listing stages in workflow order, current one checked.
- `100dvh` shell, `env(safe-area-inset-bottom)` on every sticky bottom bar and FAB.
- Tab strip, header and bottom bars are `position: sticky` / `fixed`; only the tab body scrolls.
- Landscape on a phone: viewer goes edge-to-edge and hides the bottom bar until tapped.

## 7. Open questions for you

1. Does a sub ever need to **author** markups on a phone? If yes → single-color freehand pen only. If no → pins + photos and we're done.
2. Does **Splices** matter in the field enough to sit ahead of Issues in the tab strip?
3. Should **stage changes** from mobile be restricted by role (e.g. installers can move to Install Start / Complete but not back)?
