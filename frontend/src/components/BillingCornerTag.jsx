/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Excel-style corner triangle for a release's billing tag, drawn in the
 *   bottom-right of the Job Log description cell.
 * exports:
 *   BillingCornerTag: <BillingCornerTag tag={release_tag} />
 * imports_from: [react, ../constants/releaseTags]
 * imported_by: [./JobsTableRow.jsx]
 * notes:
 *   - contracted → green; any other set tag (Change Order, MHMW Cost) → yellow
 *   - null / blank renders nothing. An untagged release has no classification to show
 *   - the two non-contracted tags share a color; the accessible name keeps them apart
 *   - JobsTableRow renders this for admins only
 */
import React from 'react';
import { releaseTagLabel } from '../constants/releaseTags';

const GREEN = '#16a34a';
const YELLOW = '#eab308';

export function BillingCornerTag({ tag }) {
    const label = releaseTagLabel(tag);
    if (!label) return null;
    const contracted = tag === 'contracted';
    const color = contracted ? GREEN : YELLOW;

    return (
        <svg
            viewBox="0 0 12 12"
            width="12"
            height="12"
            data-billing-corner={contracted ? 'contracted' : 'other'}
            role="img"
            aria-label={label}
            className="pointer-events-none absolute bottom-0 right-0"
        >
            <polygon points="12,12 12,0 0,12" fill={color} />
        </svg>
    );
}

export default BillingCornerTag;
