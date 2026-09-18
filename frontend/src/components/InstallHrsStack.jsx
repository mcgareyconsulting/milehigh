/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The two-line install-hours cell for a splice group (T9), shared by the Job Log and
 *   Subs → Invoice Paid so both read the same: the ACTUAL hours in bold on top, and a lighter
 *   second line with where they come from.
 * exports:
 *   InstallHrsStack: two-line cell body, or null when the row is not part of a splice group
 * imports_from: [react, ../utils/installHours]
 * imported_by: [frontend/src/components/JobsTableRow.jsx, frontend/src/pages/Subs.jsx]
 * invariants:
 *   - Original with splices under it: bold = what it still installs itself; below = its full
 *     budget pool.
 *   - Splice: bold = its install hours (budget + additional); below = the group's total budget
 *     pool (the parent's install_hrs, same number the original shows), plus an amber "extra"
 *     when it carries hours from outside the pool. A splice with no budget hours shows only
 *     "extra" there.
 *   - Returns null for a release outside any splice group — the caller renders its plain value.
 */
import React from 'react';

import {
    additionalHrs, budgetHrs, hasSplicedHours, installHrsOwn, installHrsTotal, isSplice, parentPoolHrs,
} from '../utils/installHours';

const AMBER = { color: 'var(--fl-amber-fg)', background: 'var(--fl-amber-bg)', borderRadius: 999, padding: '0 5px' };

export function InstallHrsStack({ row, format }) {
    const spliceParent = hasSplicedHours(row);
    const splice = isSplice(row);
    if (!spliceParent && !splice) return null;

    let bottom;
    if (spliceParent) {
        bottom = <span>{format(installHrsTotal(row))}</span>;
    } else {
        const drewBudget = (budgetHrs(row) || 0) > 0;
        const pool = parentPoolHrs(row);
        const extra = additionalHrs(row) > 0;
        bottom = (
            <>
                {(drewBudget || !extra) && <span>{pool == null ? '—' : format(pool)}</span>}
                {extra && (
                    <span className="font-semibold" style={{ ...AMBER, marginLeft: drewBudget ? 4 : 0 }}>
                        extra
                    </span>
                )}
            </>
        );
    }

    return (
        <span className="inline-flex flex-col items-center leading-tight tabular-nums">
            <span className="font-bold text-ink">{format(spliceParent ? installHrsOwn(row) : installHrsTotal(row))}</span>
            <span className="text-ink-3 whitespace-nowrap" style={{ fontSize: '0.78em' }}>{bottom}</span>
        </span>
    );
}

export default InstallHrsStack;
