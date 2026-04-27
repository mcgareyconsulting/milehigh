# #38 — Wiki / Training guide

**Source:** Board item #38 (open / normal / Job Log)
**Author:** Bill O'Neill — 2026-04-07
**Description:** "Create a Wiki / Training guide."

---

## Scope

Confirmed with Daniel 2026-04-25:

- Lives at an endpoint inside Brain.
- Static.
- Brief, high-level explanations.
- Looks nice.
- Low value — keep scope tight; doc rot is acceptable risk.

## Approach

Single React route rendering a markdown file via `react-markdown` + `@tailwindcss/typography`. No DB, no editor, no per-page routing.

## Implementation

### 1. New route

`/wiki` added to the React Router config alongside the other pages in `frontend/src/App.jsx` (or wherever routes are wired).

### 2. Dependencies

- `react-markdown`
- `@tailwindcss/typography`

Both small, both well-maintained.

### 3. Page component — `frontend/src/pages/Wiki.jsx`

Layout:
- Sticky table of contents on the left, auto-generated from `<h2>` anchors in the rendered markdown.
- Content on the right, wrapped in `prose prose-slate dark:prose-invert max-w-none`.
- Mobile: TOC collapses to a `<details>` block above the content.

### 4. Content source — `frontend/src/content/wiki.md`

Imported at build time using Vite's `?raw` suffix:

```js
import wikiContent from '../content/wiki.md?raw';
```

Single markdown file for v1. Easy to split later if useful.

### 5. v1 sections (placeholder outline; adjust while writing)

- Overview — what The Brain is and how the pieces talk
- Job Log — filters, stages, fab order, notes, review mode
- Drafting Work Load — submittals, status flow, stash review
- The Board — bug tracker basics
- Notifications — bell, @mentions, assignments
- Map — geofences, jobs
- Glossary — release, fab order, stage group, banana color, etc.

### 6. Tailwind typography plugin

If `@tailwindcss/typography` is not already enabled, add it to `tailwind.config.js` plugins. The `prose` class handles headings, lists, code, blockquotes, tables — no bespoke CSS needed.

### 7. Navbar entry

Add a "Wiki" link to `Navbar.jsx`. Visible to all authenticated users — no admin gate.

## Test plan

- [ ] `/wiki` renders for a logged-in non-admin user without errors.
- [ ] Headings produce a clickable TOC; in-page anchor scrolling works.
- [ ] Typography looks clean in both light and dark modes.
- [ ] External markdown links open in a new tab; internal links navigate within the SPA.
- [ ] Mobile viewport: TOC collapses above content; long lines wrap; no horizontal scroll.

## Out of scope (explicit)

- In-app editing.
- Search.
- Versioning / page history.
- Per-page routes (`/wiki/job-log`, etc.).
- Embedded screenshots / videos. Easy to add later — drop images in `frontend/src/content/wiki/` and reference from the markdown.
- Role-segmented content (e.g. PM-vs-drafter views).

## Risks

- **Doc rot.** Static, low-value documentation will fall out of date. Keeping sections high-level and short is the mitigation — updates stay cheap when stages, fields, or workflows change.
- **TOC fragility.** Auto-generated from `<h2>` anchors; if a section heading is renamed, anyone with a bookmark to that anchor breaks. Acceptable for low-traffic doc.
