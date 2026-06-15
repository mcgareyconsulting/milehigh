/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Job Log quick-filter control (Job Order, Ready to Ship, Paint, Paint+Fab, Fab, Review).
 *   Renders a linear button row on desktop and collapses into a single dropdown on tablet/mobile.
 * exports:
 *   JobLogQuickFilters: default — props { selectedSubset, setSelectedSubset, reviewMode, setReviewMode, compact }
 * imports_from: [react, react-dom]
 * imported_by: [../pages/JobLog.jsx]
 * invariants:
 *   - Subset and Review are mutually exclusive: selecting a subset clears reviewMode and vice versa.
 *   - Re-selecting the active subset toggles it off (linear mode); the dropdown uses an explicit "Default" entry.
 *   - The compact dropdown is portaled to document.body so it escapes the filter card's overflow:hidden.
 */
import { useState, useEffect, useRef, useLayoutEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';

// Quick-filter definitions. Review is a special boolean mode, not a subset value.
const QUICK_FILTERS = [
    { key: 'job_order',     label: 'Job Order',     activeClass: 'bg-blue-700 text-white',    title: 'Show all active releases sorted by the unified Fab Order sequence. Useful for seeing the full production queue in order.' },
    { key: 'ready_to_ship', label: 'Ready to Ship', activeClass: 'bg-emerald-600 text-white', title: 'Show only releases in Ship Planning, Store at MHMW, or Paint Complete — i.e., work that\'s finished production and ready to leave.' },
    { key: 'paint',         label: 'Paint',         activeClass: 'bg-emerald-600 text-white', title: 'Show only releases in Welded QC or Paint Start stages, sorted by Fab Order. Use to focus on jobs currently in paint.' },
    { key: 'paint_fab',     label: 'Paint+Fab',     activeClass: 'bg-emerald-600 text-white', title: 'Combined view of Paint stages (Welded QC, Paint Start, Paint Complete) followed by all Fabrication-group stages, sorted by Fab Order with Start Install date as tiebreaker.' },
    { key: 'fab',           label: 'Fab',           activeClass: 'bg-blue-700 text-white',    title: 'Show only releases in the Fabrication stage group, sorted by Fab Order. Use to focus on shop floor work.' },
    { key: 'review',        label: 'Review',        activeClass: 'bg-blue-700 text-white',    title: 'Group releases by PM (alphabetical), then by Project # ascending, with the most-complete stage first within each project. Intended for PM review meetings.' },
];

const INACTIVE_CLASS = 'bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500';
const POPOVER_WIDTH = 200;
const VIEWPORT_PAD = 8;

export default function JobLogQuickFilters({
    selectedSubset,
    setSelectedSubset,
    reviewMode,
    setReviewMode,
    compact = false,
}) {
    // Map current state to the active quick-filter key (or null for the default view).
    const activeKey = reviewMode ? 'review' : (selectedSubset || null);

    // Apply a selection by key; null clears to the default view.
    const apply = useCallback((key) => {
        if (key === 'review') {
            setSelectedSubset(null);
            setReviewMode(true);
        } else {
            setReviewMode(false);
            setSelectedSubset(key);
        }
    }, [setSelectedSubset, setReviewMode]);

    // Linear button: re-clicking the active filter toggles it off.
    const toggle = useCallback((key) => {
        if (key === activeKey) {
            apply(null);
        } else {
            apply(key);
        }
    }, [activeKey, apply]);

    // --- Compact dropdown (tablet/mobile) ---
    const [open, setOpen] = useState(false);
    const [coords, setCoords] = useState({ top: 0, left: 0, width: POPOVER_WIDTH });
    const triggerRef = useRef(null);
    const popoverRef = useRef(null);

    const updatePosition = useCallback(() => {
        const el = triggerRef.current;
        if (!el) return;
        const rect = el.getBoundingClientRect();
        const vw = window.innerWidth;
        const width = Math.min(Math.max(POPOVER_WIDTH, rect.width), vw - 2 * VIEWPORT_PAD);
        let left = rect.left;
        if (left + width > vw - VIEWPORT_PAD) left = vw - VIEWPORT_PAD - width;
        if (left < VIEWPORT_PAD) left = VIEWPORT_PAD;
        setCoords({ top: rect.bottom + 4, left, width });
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
        };
        const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
        document.addEventListener('mousedown', onMouseDown);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('mousedown', onMouseDown);
            document.removeEventListener('keydown', onKey);
        };
    }, [open]);

    if (!compact) {
        // Linear button row (desktop) — tight inline group so the whole toolbar stays on one line.
        return (
            <div className="flex items-center gap-1.5">
                {QUICK_FILTERS.map(({ key, label, activeClass, title }) => (
                    <button
                        key={key}
                        onClick={() => toggle(key)}
                        className={`px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap ${activeKey === key ? activeClass : INACTIVE_CLASS}`}
                        title={title}
                    >
                        {label}
                    </button>
                ))}
            </div>
        );
    }

    // Compact dropdown (tablet/mobile)
    const activeDef = QUICK_FILTERS.find((f) => f.key === activeKey);
    const triggerLabel = activeDef ? activeDef.label : 'Quick Filter';
    return (
        <>
            <button
                ref={triggerRef}
                type="button"
                onClick={() => setOpen((v) => !v)}
                className={`flex items-center justify-between gap-1.5 px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap min-w-[120px] ${activeDef ? activeDef.activeClass : INACTIVE_CLASS}`}
                aria-haspopup="true"
                aria-expanded={open}
                title="Quick filters: pick a preset view (Job Order, Ready to Ship, Paint, Paint+Fab, Fab, or Review)."
            >
                <span>{triggerLabel}</span>
                <span className="leading-none">▾</span>
            </button>

            {open && createPortal(
                <div
                    ref={popoverRef}
                    style={{ position: 'fixed', top: coords.top, left: coords.left, width: coords.width }}
                    className="z-[1000] bg-white dark:bg-slate-800 border-2 border-gray-300 dark:border-slate-500 rounded-md shadow-lg text-left py-1"
                >
                    <button
                        type="button"
                        onClick={() => { apply(null); setOpen(false); }}
                        className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-slate-700 ${activeKey === null ? 'font-semibold text-blue-700 dark:text-blue-300' : 'text-gray-700 dark:text-slate-200'}`}
                    >
                        Default
                    </button>
                    {QUICK_FILTERS.map(({ key, label }) => (
                        <button
                            key={key}
                            type="button"
                            onClick={() => { apply(key); setOpen(false); }}
                            className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-slate-700 ${activeKey === key ? 'font-semibold text-blue-700 dark:text-blue-300' : 'text-gray-700 dark:text-slate-200'}`}
                        >
                            {label}
                        </button>
                    ))}
                </div>,
                document.body
            )}
        </>
    );
}
