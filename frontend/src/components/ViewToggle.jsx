/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Segmented Table/Cards view toggle with localStorage persistence per page (Job Log, Archive, DWL).
 * exports:
 *   ViewToggle: Controlled segmented button. Props: value ('auto'|'table'|'cards'), onChange(next), storageKey.
 *   useViewMode: Hook — manages auto/table/cards state with localStorage persistence and returns [viewMode, setViewMode].
 * imports_from: [react]
 * imported_by: [frontend/src/pages/JobLog.jsx, frontend/src/pages/Archive.jsx, frontend/src/pages/DraftingWorkLoad.jsx]
 * invariants:
 *   - 'auto' means "follow viewport" — the consuming page resolves it via useIsTabletOrSmaller.
 *   - storageKey is page-scoped (jl_view, ar_view, dwl_view).
 */
import React, { useCallback, useState } from 'react';

const VALID_MODES = new Set(['auto', 'table', 'cards']);

export function useViewMode(storageKey, defaultMode = 'auto') {
    const [viewMode, setViewModeState] = useState(() => {
        if (typeof window === 'undefined') return defaultMode;
        const stored = localStorage.getItem(storageKey);
        return VALID_MODES.has(stored) ? stored : defaultMode;
    });

    const setViewMode = useCallback((next) => {
        if (!VALID_MODES.has(next)) return;
        setViewModeState(next);
        try {
            localStorage.setItem(storageKey, next);
        } catch {
            /* localStorage quota / private mode — non-fatal */
        }
    }, [storageKey]);

    return [viewMode, setViewMode];
}

export default function ViewToggle({ value, onChange, className = '', accent = 'blue' }) {
    const btnBase = 'px-2.5 py-1 text-xs font-semibold transition-all whitespace-nowrap';
    const active = accent === 'green' ? 'bg-green-700 text-white' : 'bg-blue-700 text-white';
    const inactive = 'bg-white dark:bg-slate-600 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500';

    return (
        <div
            role="group"
            aria-label="View mode"
            className={`inline-flex rounded border border-gray-400 dark:border-slate-500 overflow-hidden ${className}`}
        >
            <button
                type="button"
                onClick={() => onChange('table')}
                className={`${btnBase} ${value === 'table' ? active : inactive} border-r border-gray-400 dark:border-slate-500`}
                title="Table view — full data, all columns"
                aria-pressed={value === 'table'}
            >
                ☰ Table
            </button>
            <button
                type="button"
                onClick={() => onChange('cards')}
                className={`${btnBase} ${value === 'cards' ? active : inactive} border-r border-gray-400 dark:border-slate-500`}
                title="Cards view — touch-friendly, ideal for iPad and on-site PMs"
                aria-pressed={value === 'cards'}
            >
                ▣ Cards
            </button>
            <button
                type="button"
                onClick={() => onChange('auto')}
                className={`${btnBase} ${value === 'auto' ? active : inactive}`}
                title="Auto — table on desktop, cards on iPad and smaller"
                aria-pressed={value === 'auto'}
            >
                Auto
            </button>
        </div>
    );
}
