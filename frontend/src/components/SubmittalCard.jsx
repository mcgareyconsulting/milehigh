/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Touch-friendly card rendering a single Procore submittal for the iPad/Cards view of Drafting Work Load.
 * exports:
 *   default SubmittalCard: Props — submittal, onOpen, isHighlighted.
 * imports_from: [react, ../utils/formatters]
 * imported_by: [frontend/src/components/SubmittalCardGrid.jsx]
 * invariants:
 *   - Card is read-only — drag-reorder, BIC reassignment, and notes editing remain on Table view.
 */
import React from 'react';
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

function lifespanText(row) {
    const ls = row['LIFESPAN'] ?? row.lifespan_days;
    if (ls == null || ls === '') return null;
    const days = parseFloat(ls);
    if (!Number.isFinite(days)) return String(ls);
    return `${Math.round(days)}d open`;
}

function lastBicText(row) {
    const days = row['LAST BIC'] ?? row.days_since_ball_in_court_update;
    if (days == null || days === '') return null;
    const n = parseFloat(days);
    if (!Number.isFinite(n)) return String(days);
    return `${Math.round(n)}d in BIC`;
}

export default function SubmittalCard({ submittal, onOpen, isHighlighted = false }) {
    const orderNum = fmt(submittal['ORDER #']);
    const projNum = fmt(submittal['PROJ. #']);
    const projName = fmt(submittal['NAME']);
    const title = fmt(submittal['TITLE']);
    const bic = fmt(submittal['BIC']);
    const procoreStatus = fmt(submittal['PROCORE STATUS']);
    const dueDate = formatDate(submittal['DUE DATE']);
    const notes = (submittal['NOTES'] || '').toString().trim();
    const lifespan = lifespanText(submittal);
    const lastBic = lastBicText(submittal);

    return (
        <button
            type="button"
            onClick={() => onOpen?.(submittal)}
            className={`group relative text-left w-full h-full flex flex-col rounded-xl border transition-all overflow-hidden focus:outline-none focus:ring-2 focus:ring-accent-500 ${
                isHighlighted
                    ? 'border-amber-400 dark:border-amber-500 shadow-lg ring-2 ring-amber-300/50'
                    : 'border-gray-200 dark:border-slate-600 hover:border-accent-400 dark:hover:border-accent-500 hover:shadow-md'
            } bg-white dark:bg-slate-800`}
            title="Tap for full submittal details"
        >
            <div className="flex-shrink-0 flex items-center justify-between gap-2 px-3 py-2 bg-gray-50 dark:bg-slate-700/60 border-b border-gray-200 dark:border-slate-600">
                <div className="flex items-baseline gap-1.5 font-mono min-w-0">
                    <span className="text-base font-bold text-gray-900 dark:text-slate-100">#{orderNum}</span>
                    <span className="text-gray-400 dark:text-slate-500">·</span>
                    <span className="text-xs text-gray-700 dark:text-slate-200 truncate" title={`${projNum} — ${projName}`}>
                        {projNum} — {projName}
                    </span>
                </div>
                <span
                    className={`px-2 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap truncate max-w-[10rem] ${statusColor(procoreStatus)}`}
                    title={`Procore status: ${procoreStatus}`}
                >
                    {procoreStatus}
                </span>
            </div>

            <div className="flex-1 min-h-0 px-3 py-2.5 space-y-2">
                <div className="text-sm font-bold text-gray-900 dark:text-slate-100 line-clamp-2" title={title}>{title}</div>

                <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded bg-gray-50 dark:bg-slate-700/50 px-2 py-1">
                        <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-slate-400">BIC</div>
                        <div className="font-semibold text-gray-900 dark:text-slate-100 truncate" title={bic}>{bic}</div>
                    </div>
                    <div className="rounded bg-gray-50 dark:bg-slate-700/50 px-2 py-1">
                        <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-slate-400">Due</div>
                        <div className="font-semibold text-gray-900 dark:text-slate-100">{dueDate || '—'}</div>
                    </div>
                </div>

                {/* Footer row — keeps a consistent baseline across cards regardless of notes length */}
                <div className="flex items-center gap-3 flex-wrap text-[11px] text-gray-600 dark:text-slate-400 pt-1">
                    {lastBic && <span>⏱ {lastBic}</span>}
                    {lifespan && <span>📅 {lifespan}</span>}
                    <span className="ml-auto text-[10px] text-gray-400 dark:text-slate-500 group-hover:text-accent-500 dark:group-hover:text-accent-400">
                        Tap for details →
                    </span>
                </div>

                {notes && (
                    <div className="pt-1.5 border-t border-gray-100 dark:border-slate-700/60 text-xs text-gray-700 dark:text-slate-300">
                        <span className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-slate-400 mr-1">Notes:</span>
                        <span className="line-clamp-2">{notes}</span>
                    </div>
                )}
            </div>
        </button>
    );
}
