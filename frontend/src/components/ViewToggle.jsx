/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Compact View dropdown (Auto / Table / Cards) with localStorage persistence per page (Job Log, Archive, DWL).
 * exports:
 *   ViewToggle: Controlled dropdown. Props: value ('auto'|'table'|'cards'), onChange(next), className, accent.
 *   useViewMode: Hook — manages auto/table/cards state with localStorage persistence and returns [viewMode, setViewMode].
 * imports_from: [react, ./Dropdown]
 * imported_by: [frontend/src/pages/ReleasesLayout.jsx, frontend/src/pages/Archive.jsx, frontend/src/pages/DraftingWorkLoad.jsx]
 * invariants:
 *   - 'auto' is the default — "follow viewport"; the consuming page resolves it (table on desktop, cards on smaller).
 *   - storageKey is page-scoped (jl_view, ar_view, dwl_view).
 */
import React, { useCallback, useState } from 'react';
import Dropdown, { DropdownItem } from './Dropdown';

const VALID_MODES = new Set(['auto', 'table', 'cards']);

const MODE_LABELS = {
    auto: 'Auto',
    table: 'Table',
    cards: 'Cards',
};

const MODE_TITLES = {
    auto: 'Auto — table on desktop, cards on iPad and smaller',
    table: 'Table view — full data, all columns',
    cards: 'Cards view — touch-friendly, ideal for iPad and on-site PMs',
};

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

/**
 * @param value 'auto' | 'table' | 'cards'
 * @param onChange (next) => void
 * @param accent 'blue' | 'green' — green used on DWL Draft tab for the active (non-auto) trigger
 */
export default function ViewToggle({ value, onChange, className = '', accent = 'blue' }) {
    const current = VALID_MODES.has(value) ? value : 'auto';
    const isNonDefault = current !== 'auto';

    // Match Actions dropdown defaults; only override when DWL wants a green "forced" state.
    let buttonClassName;
    if (accent === 'green' && isNonDefault) {
        buttonClassName =
            'px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap inline-flex items-center gap-1.5 border bg-green-700 border-green-700 text-white hover:bg-green-800';
    }

    return (
        <div className={className || undefined}>
            <Dropdown
                label={`View: ${MODE_LABELS[current]}`}
                active={isNonDefault && accent !== 'green'}
                menuWidth={168}
                buttonClassName={buttonClassName}
            >
                <DropdownItem
                    active={current === 'auto'}
                    onClick={() => onChange('auto')}
                    title={MODE_TITLES.auto}
                >
                    Auto
                </DropdownItem>
                <DropdownItem
                    active={current === 'table'}
                    onClick={() => onChange('table')}
                    title={MODE_TITLES.table}
                >
                    ☰ Table
                </DropdownItem>
                <DropdownItem
                    active={current === 'cards'}
                    onClick={() => onChange('cards')}
                    title={MODE_TITLES.cards}
                >
                    ▣ Cards
                </DropdownItem>
            </Dropdown>
        </div>
    );
}
