/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Navigation visibility switches. These hide a surface from the app chrome
 *   WITHOUT removing its route, page, API, or service layer — flip the flag to bring
 *   the entry back everywhere at once.
 * exports:
 *   SHOW_INVOICING_NAV: whether the Invoicing report appears in the app chrome
 * imported_by: [components/AppShell.jsx, components/Rail.jsx, components/Sidebar.jsx,
 *   components/MobileNavDrawer.jsx]
 * invariants:
 *   - Chrome only. The /invoicing-report route stays registered in App.jsx and remains
 *     reachable by direct link; nothing about the feature is torn down.
 *   - Every nav surface reads the same flag, so none can drift out of sync.
 * updated_by_agent: 2026-09-02T00:00:00Z
 */

// Daniel, 2026-09-02: hide Invoicing from the chrome for now. Infrastructure stays put.
export const SHOW_INVOICING_NAV = false;
