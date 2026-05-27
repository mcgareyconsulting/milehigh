/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Standalone Job Log "Projects" filter — a searchable multi-select dropdown of
 *   "number — name" options, separate from the per-column header dropdowns.
 * exports:
 *   ProjectFilterDropdown: default — props { options, selected, onChange }
 * imports_from: [react, react-dom]
 * imported_by: [../pages/JobLog.jsx]
 * invariants:
 *   - options is [{ number, name }]; the committed/selected value is the project NAME,
 *     so it plugs into selectedProjectNames / matchesFilters unchanged.
 *   - Multi-select; commits live (each toggle calls onChange) so the active-filter chips stay in sync.
 *   - Popover is portaled to document.body and viewport-clamped (escapes the filter card's overflow).
 */
import { useState, useEffect, useRef, useMemo, useLayoutEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';

const POPOVER_WIDTH = 260;
const POPOVER_MAX_HEIGHT = 360;
const VIEWPORT_PAD = 8;

export default function ProjectFilterDropdown({ options = [], selected = [], onChange }) {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');
    const [coords, setCoords] = useState({ top: 0, left: 0, width: POPOVER_WIDTH });
    const triggerRef = useRef(null);
    const popoverRef = useRef(null);

    const selectedSet = useMemo(() => new Set(selected), [selected]);

    const updatePosition = useCallback(() => {
        const el = triggerRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const width = Math.min(POPOVER_WIDTH, vw - 2 * VIEWPORT_PAD);
        let left = rect.left;
        if (left + width > vw - VIEWPORT_PAD) left = vw - VIEWPORT_PAD - width;
        if (left < VIEWPORT_PAD) left = VIEWPORT_PAD;
        let top = rect.bottom + 4;
        if (top + POPOVER_MAX_HEIGHT > vh - VIEWPORT_PAD) {
            const above = rect.top - 4 - POPOVER_MAX_HEIGHT;
            top = above >= VIEWPORT_PAD ? above : Math.max(VIEWPORT_PAD, vh - VIEWPORT_PAD - POPOVER_MAX_HEIGHT);
        }
        setCoords({ top, left, width });
    }, []);

    useLayoutEffect(() => {
        if (!open) return undefined;
        updatePosition();
        const onScroll = () => updatePosition();
        const onResize = () => updatePosition();
        window.addEventListener('scroll', onScroll, true);
        window.addEventListener('resize', onResize);
        return () => {
            window.removeEventListener('scroll', onScroll, true);
            window.removeEventListener('resize', onResize);
        };
    }, [open, updatePosition]);

    useEffect(() => {
        if (!open) return undefined;
        const onMouseDown = (e) => {
            if (popoverRef.current && popoverRef.current.contains(e.target)) return;
            if (triggerRef.current && triggerRef.current.contains(e.target)) return;
            setOpen(false);
            setSearch('');
        };
        const onKey = (e) => { if (e.key === 'Escape') { setOpen(false); setSearch(''); } };
        document.addEventListener('mousedown', onMouseDown);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('mousedown', onMouseDown);
            document.removeEventListener('keydown', onKey);
        };
    }, [open]);

    const filteredOptions = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return options;
        return options.filter((o) =>
            o.name.toLowerCase().includes(q) || String(o.number).toLowerCase().includes(q)
        );
    }, [options, search]);

    const toggle = (name) => {
        const next = new Set(selectedSet);
        if (next.has(name)) next.delete(name);
        else next.add(name);
        onChange([...next]);
    };

    const count = selected.length;

    return (
        <>
            <button
                ref={triggerRef}
                type="button"
                onClick={() => setOpen((v) => !v)}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap ${count > 0
                    ? 'bg-blue-700 text-white'
                    : 'bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500'
                    }`}
                aria-haspopup="true"
                aria-expanded={open}
                title="Filter the job log by one or more projects (project number + name). Combine with the column filters."
            >
                <span>🏗️ Projects{count > 0 ? ` (${count})` : ''}</span>
                <span className="leading-none">▾</span>
            </button>

            {open && createPortal(
                <div
                    ref={popoverRef}
                    style={{ position: 'fixed', top: coords.top, left: coords.left, width: coords.width }}
                    className="z-[1000] bg-white dark:bg-slate-800 border-2 border-gray-300 dark:border-slate-500 rounded-md shadow-lg text-left normal-case tracking-normal font-normal text-gray-800 dark:text-slate-100"
                >
                    <div className="p-2 flex items-center gap-2 border-b border-gray-200 dark:border-slate-600">
                        <input
                            type="text"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search number or name…"
                            className="flex-1 px-2 py-1 text-xs border border-gray-300 dark:border-slate-600 rounded bg-white dark:bg-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                            autoFocus
                        />
                        {count > 0 && (
                            <button
                                type="button"
                                onClick={() => onChange([])}
                                className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap"
                            >
                                Clear
                            </button>
                        )}
                    </div>

                    <div className="max-h-72 overflow-y-auto px-2 py-1 text-xs">
                        {filteredOptions.length === 0 ? (
                            <div className="px-1 py-2 text-gray-500 dark:text-slate-400 italic">No projects</div>
                        ) : (
                            filteredOptions.map((o) => (
                                <label
                                    key={o.name}
                                    className="flex items-center gap-2 px-1 py-1 cursor-pointer select-none rounded hover:bg-gray-100 dark:hover:bg-slate-700"
                                >
                                    <input
                                        type="checkbox"
                                        checked={selectedSet.has(o.name)}
                                        onChange={() => toggle(o.name)}
                                        className="accent-blue-600"
                                    />
                                    <span className="truncate" title={`${o.number} — ${o.name}`}>
                                        <span className="font-semibold text-gray-500 dark:text-slate-400">{o.number}</span>
                                        {o.number !== '' ? ' — ' : ''}{o.name}
                                    </span>
                                </label>
                            ))
                        )}
                    </div>
                </div>,
                document.body
            )}
        </>
    );
}
