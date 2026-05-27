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
 *   - Multi-select with a draft; selection is committed via Apply (matching ColumnHeaderFilter),
 *     never on individual checkbox toggles. Clear empties the selection and closes.
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
    const [draft, setDraft] = useState(() => new Set(selected));
    const [coords, setCoords] = useState({ top: 0, left: 0, width: POPOVER_WIDTH });
    const triggerRef = useRef(null);
    const popoverRef = useRef(null);

    // Sync draft from props when the popover opens (closing without Apply discards edits).
    useEffect(() => {
        if (open) setDraft(new Set(selected));
    }, [open, selected]);

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
        setDraft((prev) => {
            const next = new Set(prev);
            if (next.has(name)) next.delete(name);
            else next.add(name);
            return next;
        });
    };

    const apply = () => {
        onChange([...draft]);
        setOpen(false);
        setSearch('');
    };

    const clear = () => {
        setDraft(new Set());
        onChange([]);
        setOpen(false);
        setSearch('');
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
                <span>Projects{count > 0 ? ` (${count})` : ''}</span>
                <span className="leading-none">▾</span>
            </button>

            {open && createPortal(
                <div
                    ref={popoverRef}
                    style={{ position: 'fixed', top: coords.top, left: coords.left, width: coords.width }}
                    className="z-[1000] bg-white dark:bg-slate-800 border-2 border-gray-300 dark:border-slate-500 rounded-md shadow-lg text-left normal-case tracking-normal font-normal text-gray-800 dark:text-slate-100"
                >
                    <div className="p-2">
                        <input
                            type="text"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search number or name…"
                            className="w-full px-2 py-1 text-xs border border-gray-300 dark:border-slate-600 rounded bg-white dark:bg-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                            autoFocus
                        />
                    </div>

                    <div className="max-h-72 overflow-y-auto px-2 pb-2 text-xs">
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
                                        checked={draft.has(o.name)}
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

                    <div className="flex border-t border-gray-200 dark:border-slate-600">
                        <button
                            type="button"
                            onClick={clear}
                            className="flex-1 px-2 py-1.5 text-xs font-medium text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-bl-md"
                        >
                            Clear
                        </button>
                        <button
                            type="button"
                            onClick={apply}
                            className="flex-1 px-2 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 border-l border-gray-200 dark:border-slate-600 rounded-br-md"
                        >
                            Apply
                        </button>
                    </div>
                </div>,
                document.body
            )}
        </>
    );
}
