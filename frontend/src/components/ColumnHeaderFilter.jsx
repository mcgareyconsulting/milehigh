/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Excel-style per-column header filter popover for the Job Log table.
 * exports:
 *   ColumnHeaderFilter: Trigger button + popover with search, sort, and value checklist.
 * imports_from: [react]
 * imported_by: [../pages/JobLog.jsx]
 * invariants:
 *   - selected is treated as a Set; '(Blanks)' is the sentinel for null/empty values.
 *   - Empty selection means "no filter on this column".
 *   - Closes on outside click or Escape; commits via Apply, never on individual checkbox toggles.
 */
import { useState, useEffect, useRef, useMemo } from 'react';

const BLANKS = '(Blanks)';

export default function ColumnHeaderFilter({
    column,
    values,
    hasBlanks,
    selected,
    onChange,
    sort,
    onSort,
    isActive,
}) {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');
    const [draft, setDraft] = useState(selected);
    const containerRef = useRef(null);
    const popoverRef = useRef(null);

    // Sync draft from props when popover opens (so "Cancel by close" doesn't persist edits)
    useEffect(() => {
        if (open) setDraft(new Set(selected));
    }, [open, selected]);

    // Outside click + Escape close
    useEffect(() => {
        if (!open) return;
        const onMouseDown = (e) => {
            if (popoverRef.current && popoverRef.current.contains(e.target)) return;
            if (containerRef.current && containerRef.current.contains(e.target)) return;
            setOpen(false);
            setSearch('');
        };
        const onKey = (e) => {
            if (e.key === 'Escape') {
                setOpen(false);
                setSearch('');
            }
        };
        document.addEventListener('mousedown', onMouseDown);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('mousedown', onMouseDown);
            document.removeEventListener('keydown', onKey);
        };
    }, [open]);

    const filteredValues = useMemo(() => {
        const q = search.trim().toLowerCase();
        if (!q) return values;
        return values.filter((v) => v.toLowerCase().includes(q));
    }, [values, search]);

    const showBlanks = hasBlanks && (!search.trim() || BLANKS.toLowerCase().includes(search.trim().toLowerCase()));
    const optionCount = filteredValues.length + (showBlanks ? 1 : 0);
    const allChecked = optionCount > 0
        && filteredValues.every((v) => draft.has(v))
        && (!showBlanks || draft.has(BLANKS));

    const toggleValue = (v) => {
        setDraft((prev) => {
            const next = new Set(prev);
            if (next.has(v)) next.delete(v);
            else next.add(v);
            return next;
        });
    };

    const toggleAllVisible = () => {
        setDraft((prev) => {
            const next = new Set(prev);
            if (allChecked) {
                filteredValues.forEach((v) => next.delete(v));
                if (showBlanks) next.delete(BLANKS);
            } else {
                filteredValues.forEach((v) => next.add(v));
                if (showBlanks) next.add(BLANKS);
            }
            return next;
        });
    };

    const apply = () => {
        onChange(draft);
        setOpen(false);
        setSearch('');
    };

    const clear = () => {
        setDraft(new Set());
        onChange(new Set());
        if (sort?.column === column) onSort(null);
        setOpen(false);
        setSearch('');
    };

    const sortDir = sort?.column === column ? sort.direction : null;

    return (
        <span ref={containerRef} className="relative inline-flex" onMouseDown={(e) => e.stopPropagation()}>
            <button
                type="button"
                onClick={(e) => {
                    e.stopPropagation();
                    setOpen((v) => !v);
                }}
                className={`ml-1 inline-flex items-center justify-center w-4 h-4 rounded hover:bg-gray-200 dark:hover:bg-slate-600 ${isActive ? 'text-blue-600 dark:text-blue-400' : 'text-gray-500 dark:text-slate-400'}`}
                aria-label={`Filter ${column}`}
                aria-haspopup="true"
                aria-expanded={open}
            >
                {isActive ? (
                    <svg viewBox="0 0 16 16" width="10" height="10" fill="currentColor" aria-hidden="true">
                        <path d="M1 2h14l-5.5 6.5V14L6.5 12V8.5L1 2z" />
                    </svg>
                ) : (
                    <svg viewBox="0 0 16 16" width="10" height="10" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                        <path d="M3 4l5 6 5-6H3z" strokeLinejoin="round" strokeLinecap="round" />
                    </svg>
                )}
            </button>

            {open && (
                <div
                    ref={popoverRef}
                    className="absolute right-0 top-full mt-1 z-30 w-56 bg-white dark:bg-slate-800 border-2 border-gray-300 dark:border-slate-500 rounded-md shadow-lg text-left normal-case tracking-normal font-normal text-gray-800 dark:text-slate-100"
                    onClick={(e) => e.stopPropagation()}
                >
                    <div className="flex border-b border-gray-200 dark:border-slate-600">
                        <button
                            type="button"
                            onClick={() => onSort('asc')}
                            className={`flex-1 px-2 py-1.5 text-xs font-medium hover:bg-gray-100 dark:hover:bg-slate-700 ${sortDir === 'asc' ? 'bg-blue-50 dark:bg-slate-700 text-blue-700 dark:text-blue-300' : ''}`}
                        >
                            Sort A→Z
                        </button>
                        <button
                            type="button"
                            onClick={() => onSort('desc')}
                            className={`flex-1 px-2 py-1.5 text-xs font-medium border-l border-gray-200 dark:border-slate-600 hover:bg-gray-100 dark:hover:bg-slate-700 ${sortDir === 'desc' ? 'bg-blue-50 dark:bg-slate-700 text-blue-700 dark:text-blue-300' : ''}`}
                        >
                            Sort Z→A
                        </button>
                    </div>

                    <div className="p-2">
                        <input
                            type="text"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            placeholder="Search…"
                            className="w-full px-2 py-1 text-xs border border-gray-300 dark:border-slate-600 rounded bg-white dark:bg-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                            autoFocus
                        />
                    </div>

                    <div className="max-h-56 overflow-y-auto px-2 pb-2 text-xs">
                        {optionCount === 0 ? (
                            <div className="px-1 py-2 text-gray-500 dark:text-slate-400 italic">No values</div>
                        ) : (
                            <>
                                <label className="flex items-center gap-2 px-1 py-1 cursor-pointer select-none rounded hover:bg-gray-100 dark:hover:bg-slate-700 font-medium">
                                    <input
                                        type="checkbox"
                                        checked={allChecked}
                                        onChange={toggleAllVisible}
                                        className="accent-blue-600"
                                    />
                                    <span>(Select All)</span>
                                </label>
                                {showBlanks && (
                                    <label className="flex items-center gap-2 px-1 py-1 cursor-pointer select-none rounded hover:bg-gray-100 dark:hover:bg-slate-700 italic text-gray-600 dark:text-slate-300">
                                        <input
                                            type="checkbox"
                                            checked={draft.has(BLANKS)}
                                            onChange={() => toggleValue(BLANKS)}
                                            className="accent-blue-600"
                                        />
                                        <span>{BLANKS}</span>
                                    </label>
                                )}
                                {filteredValues.map((v) => (
                                    <label
                                        key={v}
                                        className="flex items-center gap-2 px-1 py-1 cursor-pointer select-none rounded hover:bg-gray-100 dark:hover:bg-slate-700"
                                    >
                                        <input
                                            type="checkbox"
                                            checked={draft.has(v)}
                                            onChange={() => toggleValue(v)}
                                            className="accent-blue-600"
                                        />
                                        <span className="truncate" title={v}>{v}</span>
                                    </label>
                                ))}
                            </>
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
                </div>
            )}
        </span>
    );
}
