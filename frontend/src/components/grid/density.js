/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The shared size→content-density convention for the K2 grid. A panel's size class
 *   is not just geometry: resizing Submittals or Releases is how a user says "show me more of
 *   this". Without one convention every panel would invent its own idea of how many rows fit
 *   at height 3, and the dashboard would read inconsistently. Capacities are deliberately
 *   slightly conservative — Panel bodies scroll, so under-filling looks fine and over-filling
 *   would hide rows behind a scrollbar the user didn't ask for.
 * exports:
 *   listCapacity(rows): approximate list items that fit at a given height class
 *   LIST_CAPACITY: the raw table, for tests and callers that want the whole map
 * imports_from: []
 * imported_by: [pages/GridDemo.jsx, pages/ProjectDetail.jsx (D1)]
 * invariants:
 *   - Monotonic: a taller panel never shows fewer items than a shorter one.
 */

// Derived from ROW_UNIT_PX (96) + 12px gaps, less ~42px header and ~28px padding, at an
// approx 26px list row. Rendered height = rows*96 + (rows-1)*12.
export const LIST_CAPACITY = {
  1: 2,
  2: 5,
  3: 9,
  4: 13,
};

export function listCapacity(rows) {
  return LIST_CAPACITY[rows] ?? LIST_CAPACITY[2];
}
