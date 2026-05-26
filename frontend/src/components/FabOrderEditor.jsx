/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Self-contained, table-free Fab Order control for the touch card views. A compact numeric
 *   input that commits on blur/Enter, reverts invalid input or Escape, and writes through
 *   jobsApi.updateFabOrder then refetches via onUpdate. Highlights duplicate fab orders within the
 *   stage group the same way the desktop table does, and locks while the row is complete/grayed.
 * exports:
 *   default FabOrderEditor: Props — row, onUpdate, stageToGroup, duplicateFabOrders, stageGroupDupColors, className.
 * imports_from: [react, ../services/jobsApi, ../utils/stageProgress]
 * imported_by: [frontend/src/components/JobLogRow.jsx]
 * invariants:
 *   - Commit only on a changed, finite number; empty clears the value; invalid reverts.
 *   - stopPropagation so editing never toggles the parent card row.
 */
import React, { useEffect, useState } from 'react';
import { jobsApi } from '../services/jobsApi';
import { isCompleteStage } from '../utils/stageProgress';

const toInputValue = (v) => (v === null || v === undefined ? '' : String(v));

export default function FabOrderEditor({
    row,
    onUpdate,
    stageToGroup = null,
    duplicateFabOrders = null,
    stageGroupDupColors = null,
    className = '',
}) {
    const job = row['Job #'];
    const release = row['Release #'];
    const stage = row['Stage'] || 'Released';
    const fabOrder = row['Fab Order'];

    const [value, setValue] = useState(toInputValue(fabOrder));
    const [saving, setSaving] = useState(false);

    useEffect(() => { setValue(toInputValue(fabOrder)); }, [fabOrder]);

    const grayed = isCompleteStage(stage);
    const readOnly = !onUpdate;

    const group = stageToGroup?.[stage] || 'FABRICATION';
    const groupDupes = duplicateFabOrders?.get?.(group);
    const isDuplicate = !!groupDupes && fabOrder != null && fabOrder >= 3 && groupDupes.has(fabOrder);
    const dupColor = isDuplicate ? (stageGroupDupColors?.[group] || '#f97316') : null;

    const commit = (raw) => {
        const trimmed = raw.trim();
        if (trimmed === '') {
            if (fabOrder === null || fabOrder === undefined) return;        // already empty
            return save(null);                                              // clear → null (route rejects '')
        }
        const parsed = parseFloat(trimmed);
        if (isNaN(parsed) || !isFinite(parsed)) {
            setValue(toInputValue(fabOrder));                                // invalid → revert
            return;
        }
        if (parsed === (fabOrder ?? null)) return;                           // unchanged
        return save(parsed);
    };

    // next is a finite number to set, or null to clear.
    const save = async (next) => {
        setSaving(true);
        try {
            await jobsApi.updateFabOrder(job, release, next);
            if (onUpdate) onUpdate();
        } catch (err) {
            alert(`Failed to update fab order: ${err.message}`);
            setValue(toInputValue(fabOrder));
        } finally {
            setSaving(false);
        }
    };

    if (readOnly) {
        return (
            <span className="inline-block text-xs tabular-nums text-gray-900 dark:text-slate-100 text-center" style={{ minWidth: '2rem' }}>
                {toInputValue(fabOrder) || '—'}
            </span>
        );
    }

    return (
        <input
            type="text"
            inputMode="numeric"
            value={value}
            disabled={saving || grayed}
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => setValue(e.target.value)}
            onBlur={(e) => commit(e.target.value)}
            onKeyDown={(e) => {
                if (e.key === 'Enter') e.target.blur();
                else if (e.key === 'Escape') { setValue(toInputValue(fabOrder)); e.target.blur(); }
            }}
            placeholder="—"
            title="Fab Order"
            aria-label="Fab Order"
            className={`w-10 text-center text-xs tabular-nums rounded border px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 ${
                isDuplicate
                    ? 'text-white font-bold border-transparent'
                    : 'bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 border-gray-300 dark:border-slate-500'
            } ${(saving || grayed) ? 'opacity-50 cursor-not-allowed' : ''} ${className}`}
            style={isDuplicate ? { backgroundColor: dupColor } : undefined}
        />
    );
}
