/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Small toolbar dropdown — a trigger button (label + chevron) that toggles a menu of items.
 *   Closes on outside click, Escape, or item selection. Used to collapse toolbar buttons into
 *   "Actions" / "Views" menus on Job Log and Drafting WL.
 * exports:
 *   default Dropdown: Props — label, icon, active, disabled, align ('left'|'right'), menuWidth, buttonClassName, children.
 *   DropdownItem: Menu row. Props — onClick, disabled, active, icon, children.
 * imports_from: [react]
 * imported_by: [src/pages/JobLog.jsx, src/pages/DraftingWorkLoad.jsx]
 * invariants:
 *   - Trigger styling matches the existing toolbar buttons by default; pass buttonClassName to override.
 *   - Menu is absolutely positioned below the trigger; the parent toolbar is not overflow-clipped downward.
 */
import React, { useEffect, useRef, useState } from 'react';

const DEFAULT_TRIGGER = 'px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap inline-flex items-center gap-1.5 border';
const TRIGGER_REST = 'bg-white dark:bg-slate-600 border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500';
const TRIGGER_ACTIVE = 'bg-blue-700 border-blue-700 text-white hover:bg-blue-800';

function Chevron() {
    return (
        <svg width="10" height="10" viewBox="0 0 11 11" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="opacity-70">
            <path d="M2 4l3.5 3.5L9 4" />
        </svg>
    );
}

export default function Dropdown({ label, icon, active = false, disabled = false, align = 'left', menuWidth = 200, buttonClassName, children }) {
    const [open, setOpen] = useState(false);
    const ref = useRef(null);

    useEffect(() => {
        if (!open) return undefined;
        const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
        document.addEventListener('mousedown', onDown);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('mousedown', onDown);
            document.removeEventListener('keydown', onKey);
        };
    }, [open]);

    const triggerCls = buttonClassName || `${DEFAULT_TRIGGER} ${active ? TRIGGER_ACTIVE : TRIGGER_REST} ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`;

    return (
        <div ref={ref} className="relative inline-block">
            <button
                type="button"
                disabled={disabled}
                onClick={() => setOpen((o) => !o)}
                className={triggerCls}
                aria-haspopup="true"
                aria-expanded={open}
            >
                {icon}{label}<Chevron />
            </button>
            {open && (
                <div
                    className="absolute z-50 mt-1 rounded-md border border-gray-300 dark:border-slate-600 bg-white dark:bg-slate-800 shadow-lg py-1"
                    style={{ minWidth: menuWidth, [align === 'right' ? 'right' : 'left']: 0 }}
                    onClick={() => setOpen(false)}
                >
                    {children}
                </div>
            )}
        </div>
    );
}

export function DropdownItem({ onClick, disabled = false, active = false, icon, title, children }) {
    return (
        <button
            type="button"
            disabled={disabled}
            onClick={onClick}
            title={title}
            className={`w-full text-left px-3.5 py-2 text-sm flex items-center gap-2 whitespace-nowrap transition-colors ${
                disabled
                    ? 'opacity-40 cursor-not-allowed text-gray-700 dark:text-slate-200'
                    : active
                        ? 'bg-blue-50 dark:bg-slate-700 text-blue-700 dark:text-blue-300 font-semibold'
                        : 'text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700'
            }`}
        >
            {icon}<span className="flex-1">{children}</span>
            {active && <span className="text-blue-600 dark:text-blue-400">✓</span>}
        </button>
    );
}
