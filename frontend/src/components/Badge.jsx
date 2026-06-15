/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Tinted, ring-bordered pill used across the invoicing report and its release-history modal.
 * exports:
 *   Badge: span pill with an optional leading dot, colored by a TINT family key.
 * imports_from: [../utils/invoicingFormat]
 * imported_by: [pages/InvoicingReport.jsx, components/ReleaseHistoryModal.jsx]
 */
import { TINT, KIND_META } from '../utils/invoicingFormat';

export function Badge({ tint = 'slate', dot = false, className = '', children }) {
    return (
        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium ring-1 ring-inset ${TINT[tint]} ${className}`}>
            {dot && <span className={`w-2 h-2 rounded-full ${KIND_META[dot]?.dot || 'bg-current'}`} />}
            {children}
        </span>
    );
}

export default Badge;
