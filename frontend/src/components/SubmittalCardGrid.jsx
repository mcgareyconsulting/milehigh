/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Responsive card grid for Drafting Work Load — renders SubmittalCard tiles, opens SubmittalDetailsModal on tap.
 * exports:
 *   default SubmittalCardGrid: Props — rows, jumpToTarget, hasData, iconSize.
 * imports_from: [react, ./SubmittalCard, ./SubmittalDetailsModal]
 * imported_by: [frontend/src/pages/DraftingWorkLoad.jsx]
 * invariants:
 *   - Grid: 1 col on phone, 2 col on iPad, 3 col on 27", 4 col on 3xl.
 */
import React, { useState } from 'react';
import SubmittalCard from './SubmittalCard';
import { SubmittalDetailsModal } from './SubmittalDetailsModal';

export default function SubmittalCardGrid({ rows, jumpToTarget = null }) {
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
        <div className="flex-1 min-h-0 overflow-auto p-2 sm:p-3 3xl:p-5">
            <div className="grid gap-3 sm:gap-4 grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 3xl:grid-cols-4">
                {rows.map((row) => (
                    <SubmittalCard
                        key={row.id}
                        submittal={row}
                        onOpen={setSelected}
                        isHighlighted={isHighlighted(row)}
                    />
                ))}
            </div>

            <SubmittalDetailsModal
                isOpen={selected != null}
                onClose={() => setSelected(null)}
                submittal={selected}
            />
        </div>
    );
}
