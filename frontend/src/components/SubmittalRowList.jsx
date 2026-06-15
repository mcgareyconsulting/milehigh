/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Vertical list of SubmittalRow components for the iPad/touch view of Drafting Work Load. Replaces the prior card-grid layout with dense, collapsible read-only rows.
 * exports:
 *   default SubmittalRowList: Props — rows, jumpToTarget, canEditRel, onRelAssigned.
 * imports_from: [react, ./SubmittalRow, ./SubmittalDetailsModal]
 * imported_by: [frontend/src/pages/DraftingWorkLoad.jsx]
 */
import React, { useState } from 'react';
import SubmittalRow from './SubmittalRow';
import { SubmittalDetailsModal } from './SubmittalDetailsModal';

export default function SubmittalRowList({ rows, jumpToTarget = null, canEditRel = false, onRelAssigned }) {
    const [selected, setSelected] = useState(null);

    const isHighlighted = (row) => {
        if (!jumpToTarget) return false;
        const sid = row['Submittals Id'] ?? row.submittal_id ?? '';
        return String(sid) === jumpToTarget;
    };

    if (!rows || rows.length === 0) {
        return (
            <div className="flex items-center justify-center py-16 text-center text-gray-500 dark:text-slate-400 font-medium">
                No records match the selected filters.
            </div>
        );
    }

    return (
        <div className="flex-1 min-h-0 overflow-auto">
            <div>
                {rows.map((row) => (
                    <SubmittalRow
                        key={row.id}
                        submittal={row}
                        isHighlighted={isHighlighted(row)}
                        onOpenDetails={setSelected}
                    />
                ))}
            </div>

            <SubmittalDetailsModal
                isOpen={selected != null}
                onClose={() => setSelected(null)}
                submittal={selected}
                canEditRel={canEditRel}
                onRelAssigned={onRelAssigned}
            />
        </div>
    );
}
