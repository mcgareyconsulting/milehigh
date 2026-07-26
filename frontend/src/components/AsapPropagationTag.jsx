/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared visuals for out-of-department ASAP releases propagated into the Paint / Ready-to-Ship Job Log filters. Surfaces hot upstream releases so a downstream foreman sees them without losing their primary work list.
 * exports:
 *   ASAP_PROPAGATED_ROW_CLASS: left-accent class applied to a propagated row in every view.
 *   ASAP_DIVIDER_BOX_CLASS: shared padding/color tokens for the divider wrapper (each view adds its own border/structure classes).
 *   AsapDividerLabel: section-header label text for the divider that separates propagated rows from in-department rows.
 * imports_from: [react]
 * imported_by: [JobsTableRow.jsx, JobLogCard.jsx, JobLogCardGrid.jsx, pages/JobLogContent.jsx]
 */
import React from 'react';

// Red left accent marking a propagated (out-of-department) ASAP row.
export const ASAP_PROPAGATED_ROW_CLASS = 'border-l-2 border-l-red-500';

// Common padding/colour tokens for the divider wrapper; each renderer appends the
// structural classes its element needs (e.g. `border-y`, or `border rounded-lg col-span-full`).
export const ASAP_DIVIDER_BOX_CLASS = 'px-3 py-1.5 text-center bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800';

export function AsapDividerLabel({ count }) {
    return (
        <span className="inline-flex items-center gap-1.5 text-sm font-bold uppercase tracking-wide text-red-700 dark:text-red-300">
            <span>Out-of-department ASAPs</span>
            <span className="font-medium normal-case tracking-normal text-red-600/80 dark:text-red-300/80">
                — hot releases in earlier departments ({count})
            </span>
        </span>
    );
}
