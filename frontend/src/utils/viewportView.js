/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Resolve Auto/Table/Cards against viewport buckets. Rotating an iPad
 *   crosses 1024px (lg) and 1280px (xl) and swaps the mounted tree — that is
 *   BUG-14. Callers must keep modal and scroll state on a parent that survives
 *   the swap, not inside JobLogCardGrid / JobsTableRow / SubmittalRowList.
 * exports:
 *   resolveJobLogView: Job Log (cards forced below lg; Auto = cards on tablet).
 *   resolveAutoCardsBelowXl: Archive / DWL (Auto = cards below 1280px).
 *   viewSwapsOnRotate: true when two snapshots mount different trees.
 * imports_from: []
 * imported_by: [frontend/src/pages/ReleasesLayout.jsx, frontend/src/pages/Archive.jsx,
 *   frontend/src/pages/DraftingWorkLoad.jsx]
 */

export function resolveJobLogView({ isMobile, isTablet, isBelowLg, viewMode }) {
    if (isMobile) return 'mobilecard';
    if (isBelowLg) return 'cards';
    if (viewMode === 'table') return 'table';
    if (viewMode === 'cards') return 'cards';
    return isTablet ? 'cards' : 'table';
}

export function resolveAutoCardsBelowXl(viewMode, isTabletOrSmaller) {
    if (viewMode === 'table' || viewMode === 'cards') return viewMode;
    return isTabletOrSmaller ? 'cards' : 'table';
}

/** True when rotating from `from` to `to` would unmount the current list tree. */
export function viewSwapsOnRotate(fromView, toView) {
    const listKind = (v) => (v === 'table' ? 'table' : 'cards');
    return listKind(fromView) !== listKind(toView);
}
