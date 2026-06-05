/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Dense, table-like row rendering a single Procore submittal for the iPad/touch view of Drafting Work Load. Critical fields visible by default; chevron expands a read-only panel of the remaining fields.
 * exports:
 *   default SubmittalRow: Props — submittal, isHighlighted, onOpenDetails.
 * imports_from: [react, ../utils/formatters]
 * imported_by: [frontend/src/components/SubmittalRowList.jsx]
 * invariants:
 *   - Read-only — preserves the SubmittalCard invariant that BIC reassignment, drag reorder, and notes editing stay on the desktop Table view.
 *   - Critical (collapsed) fields: ORDER #, Project Name + TITLE subtext, PROCORE STATUS, DUE DATE.
 */
import React, { useState } from 'react';
import { formatDate } from '../utils/formatters';

const fmt = (v) => (v == null || v === '' ? '—' : String(v));

function statusColor(status) {
    const s = (status || '').toLowerCase();
    if (s.includes('approved')) return 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200';
    if (s.includes('reject')) return 'bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200';
    if (s.includes('open')) return 'bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200';
    if (s.includes('draft')) return 'bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200';
    if (s.includes('pending') || s.includes('progress')) return 'bg-indigo-100 dark:bg-indigo-900/40 text-indigo-800 dark:text-indigo-200';
    return 'bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-slate-200';
}

function FieldPair({ label, value }) {
    return (
        <div className="flex flex-col gap-0.5 px-2 py-1 rounded bg-white dark:bg-slate-700/40 border border-gray-100 dark:border-slate-600/60">
            <span className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-slate-400">{label}</span>
            <span className="text-xs text-gray-900 dark:text-slate-100 break-words">{value}</span>
        </div>
    );
}

export default function SubmittalRow({ submittal, isHighlighted = false, onOpenDetails }) {
    const [expanded, setExpanded] = useState(false);

    const orderNum = fmt(submittal['ORDER #']);
    const projNum = fmt(submittal['PROJ. #']);
    const projName = fmt(submittal['NAME']);
    const title = (submittal['TITLE'] || '').toString().trim();
    const bic = fmt(submittal['BIC']);
    const procoreStatus = fmt(submittal['PROCORE STATUS']);
    const dueDate = formatDate(submittal['DUE DATE']);
    const notes = (submittal['NOTES'] || '').toString().trim();

    const containerCls = `border-b border-gray-200 dark:border-slate-700 ${
        isHighlighted ? 'bg-amber-50 dark:bg-amber-900/20' : ''
    }`;

    return (
        <div className={containerCls}>
            <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                aria-expanded={expanded}
                className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-slate-700/60 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:ring-inset"
            >
                <span className="shrink-0 font-mono text-sm font-semibold text-gray-900 dark:text-slate-100">
                    #{orderNum}
                </span>

                <span className="flex-1 min-w-0 truncate text-sm text-gray-900 dark:text-slate-100">
                    <span className="font-semibold">{projName}</span>
                    {title ? (
                        <span className="text-gray-500 dark:text-slate-400 ml-1">— {title}</span>
                    ) : null}
                </span>

                <span
                    className={`shrink-0 px-2 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap max-w-[10rem] truncate ${statusColor(procoreStatus)}`}
                    title={`Procore status: ${procoreStatus}`}
                >
                    {procoreStatus}
                </span>

                <span className="shrink-0 tabular-nums text-xs text-gray-700 dark:text-slate-300 w-16 text-right">
                    {dueDate || '—'}
                </span>

                <span
                    className={`shrink-0 inline-block transition-transform text-gray-500 dark:text-slate-400 ${expanded ? 'rotate-90' : ''}`}
                    aria-hidden="true"
                >
                    ▸
                </span>
            </button>

            {expanded && (
                <div
                    className="px-3 py-2 bg-gray-50 dark:bg-slate-800/60 border-t border-gray-200 dark:border-slate-700"
                    onClick={(e) => e.stopPropagation()}
                >
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                        <FieldPair label="Proj #" value={projNum} />
                        <FieldPair label="BIC" value={bic} />
                    </div>

                    {notes && (
                        <div className="mt-2 pt-2 border-t border-gray-200 dark:border-slate-700">
                            <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-slate-400 mb-1">Notes</div>
                            <div className="text-xs text-gray-800 dark:text-slate-200 whitespace-pre-wrap break-words">{notes}</div>
                        </div>
                    )}

                    {onOpenDetails && (
                        <div className="mt-2 flex justify-end">
                            <button
                                type="button"
                                onClick={(e) => { e.stopPropagation(); onOpenDetails(submittal); }}
                                className="text-xs text-accent-600 dark:text-accent-400 hover:underline"
                            >
                                Open full details →
                            </button>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
