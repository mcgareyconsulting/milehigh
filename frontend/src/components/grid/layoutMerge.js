/**
 * @milehigh-header
 * schema_version: 2
 * purpose: Pure reconciliation for the K2 grid engine. Persistence stores only a layout
 *   list — per panel: id, size class, and whether it's hidden — never the panels themselves.
 *   So a saved layout can reference panels since removed, miss panels since added, or carry
 *   a size a panel no longer allows. This merges a saved layout against the canonical panel
 *   set the page actually renders. No React, no I/O — trivially unit-testable.
 * exports:
 *   mergeLayout(panels, savedLayout): [{id, span, rows, hidden}]  reconciled layout
 *   DEFAULT_SIZES: width classes a panel allows unless it says otherwise
 *   DEFAULT_ROW_SIZES: height classes a panel allows unless it says otherwise
 * imports_from: []
 * imported_by: [components/grid/useGridLayout.js, components/grid/PanelGrid.jsx, tests]
 * invariants:
 *   - Output has exactly one entry per canonical panel — never a stale id, never a missing
 *     one. Consumers can render straight from it.
 *   - span/rows are always one of the panel's allowed sizes.
 * schema history:
 *   v1 stored a bare id array (["releases", ...]); v2 added {span, hidden}. Both are still
 *   accepted on read, so an older layout upgrades in place instead of being discarded.
 */

export const DEFAULT_SIZES = [1, 2, 3];
export const DEFAULT_ROW_SIZES = [1, 2, 3, 4];
const DEFAULT_ROWS = 2;

// Accepts both the v2 object form and the v1 bare-string form.
function normalizeSaved(entry) {
  if (typeof entry === 'string') return { id: entry };
  if (entry && typeof entry === 'object' && typeof entry.id === 'string') return entry;
  return null;
}

function allowedSizes(panel) {
  const sizes = Array.isArray(panel.sizes) && panel.sizes.length ? panel.sizes : DEFAULT_SIZES;
  return sizes.filter(s => DEFAULT_SIZES.includes(s));
}

function allowedRowSizes(panel) {
  const sizes = Array.isArray(panel.rowSizes) && panel.rowSizes.length
    ? panel.rowSizes
    : DEFAULT_ROW_SIZES;
  return sizes.filter(s => DEFAULT_ROW_SIZES.includes(s));
}

/** Pick the width to render: the saved one if the panel still allows it, else its default. */
function resolveSpan(panel, savedSpan) {
  const sizes = allowedSizes(panel);
  if (!sizes.length) return 1;
  const fallback = sizes.includes(panel.span) ? panel.span : sizes[0];
  return sizes.includes(savedSpan) ? savedSpan : fallback;
}

/** Pick the height to render, same rules as width. */
function resolveRows(panel, savedRows) {
  const sizes = allowedRowSizes(panel);
  if (!sizes.length) return DEFAULT_ROWS;
  const preferred = panel.rows ?? DEFAULT_ROWS;
  const fallback = sizes.includes(preferred) ? preferred : sizes[0];
  return sizes.includes(savedRows) ? savedRows : fallback;
}

/**
 * @param {Array} panels - canonical panel descriptors in default order. Each may carry
 *   `span`/`sizes` (default + allowed widths) and `rows`/`rowSizes` (default + allowed
 *   heights, in grid row units).
 * @param {Array|null|undefined} savedLayout - persisted layout (objects, or v1 id strings).
 * @returns {Array<{id: string, span: number, rows: number, hidden: boolean}>}
 */
export function mergeLayout(panels, savedLayout) {
  const canonical = Array.isArray(panels) ? panels : [];
  const byId = new Map(canonical.map(p => [p.id, p]));

  const saved = Array.isArray(savedLayout) ? savedLayout : [];
  const seen = new Set();
  const out = [];

  for (const raw of saved) {
    const entry = normalizeSaved(raw);
    if (!entry) continue;
    const panel = byId.get(entry.id);
    // Drop ids that no longer map to a panel, and any duplicate.
    if (!panel || seen.has(entry.id)) continue;
    seen.add(entry.id);
    out.push({
      id: entry.id,
      span: resolveSpan(panel, entry.span),
      rows: resolveRows(panel, entry.rows),
      hidden: entry.hidden === true,
    });
  }

  // Panels added since the layout was saved: keep their canonical position, default size,
  // and show them (a new panel appearing hidden would look like a bug).
  for (const panel of canonical) {
    if (seen.has(panel.id)) continue;
    seen.add(panel.id);
    out.push({
      id: panel.id,
      span: resolveSpan(panel, undefined),
      rows: resolveRows(panel, undefined),
      hidden: false,
    });
  }

  return out;
}
