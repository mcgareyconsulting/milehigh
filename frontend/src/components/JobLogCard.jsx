/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Trello-style card rendering a single job release for the iPad/touch-friendly card view of Job Log and Archive.
 * exports:
 *   default JobLogCard: Card component. Props: job, onOpen (tap handler), stageGroupColors, stageToGroup, isHighlighted, isCompact.
 * imports_from: [react, ./StageIconRow, ../utils/stageProgress, ../utils/formatters]
 * imported_by: [frontend/src/components/JobLogCardGrid.jsx]
 * invariants:
 *   - Card is read-only — all editing flows happen by switching to Table view.
 *   - Tap anywhere on the card body opens the parent's onOpen callback (typically JobDetailsModal).
 */
import React from 'react';
import { StageIconRow } from './StageIconRow';
import { isCompleteStage } from '../utils/stageProgress';
import { formatDateShort } from '../utils/formatters';

const fmt = (v) => (v == null || v === '' ? '—' : String(v));
const fmtHrs = (v) => {
    if (v == null || v === '') return '—';
    const n = parseFloat(v);
    return Number.isFinite(n) ? n.toFixed(2) : '—';
};

function stagePillStyle(stage, stageToGroup, stageGroupColors) {
    const group = stageToGroup?.[stage];
    const c = stageGroupColors?.[group];
    if (!c) return null;
    return {
        backgroundColor: c.light,
        color: c.text,
        borderColor: c.border,
        borderWidth: '1px',
        borderStyle: 'solid',
    };
}

function progressChip(value, label) {
    const v = (value == null ? '' : String(value)).trim();
    if (!v) return null;
    const isX = v.toLowerCase() === 'x';
    const cls = isX
        ? 'bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200 border-emerald-300 dark:border-emerald-700'
        : 'bg-blue-50 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 border-blue-300 dark:border-blue-700';
    return (
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${cls}`}>
            <span className="opacity-70">{label}</span>
            <span>{isX ? '✓' : v}</span>
        </span>
    );
}

export default function JobLogCard({
    job,
    onOpen,
    stageToGroup,
    stageGroupColors,
    isHighlighted = false,
    iconSize = 20,
}) {
    const jobNum = fmt(job['Job #']);
    const release = fmt(job['Release #']);
    const jobName = fmt(job['Job']);
    const description = fmt(job['Description']);
    const stage = job['Stage'] || 'Released';
    const startInstall = formatDateShort(job['Start install']);
    const compEta = formatDateShort(job['Comp. ETA']);
    const notes = (job['Notes'] || '').toString().trim();
    const complete = isCompleteStage(stage);

    return (
        <button
            type="button"
            onClick={() => onOpen?.(job)}
            className={`group relative text-left w-full h-full flex flex-col rounded-xl border transition-all overflow-hidden focus:outline-none focus:ring-2 focus:ring-accent-500 ${
                isHighlighted
                    ? 'border-amber-400 dark:border-amber-500 shadow-lg ring-2 ring-amber-300/50'
                    : 'border-gray-200 dark:border-slate-600 hover:border-accent-400 dark:hover:border-accent-500 hover:shadow-md'
            } bg-white dark:bg-slate-800 ${complete ? 'opacity-90' : ''}`}
            title="Tap for full details"
        >
            {/* Header strip */}
            <div className="flex-shrink-0 flex items-center justify-between gap-2 px-3 py-2 bg-gray-50 dark:bg-slate-700/60 border-b border-gray-200 dark:border-slate-600">
                <div className="flex items-baseline gap-1.5 font-mono">
                    <span className="text-base font-bold text-gray-900 dark:text-slate-100">{jobNum}</span>
                    <span className="text-gray-400 dark:text-slate-500">·</span>
                    <span className="text-sm text-gray-700 dark:text-slate-200">{release}</span>
                </div>
                <span
                    className="px-2 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap truncate max-w-[14rem] bg-gray-200 dark:bg-slate-600 text-gray-800 dark:text-slate-100"
                    style={stagePillStyle(stage, stageToGroup, stageGroupColors) || undefined}
                    title={`Stage: ${stage}`}
                >
                    {stage}
                </span>
            </div>

            {/* Body */}
            <div className="flex-1 min-h-0 px-3 py-2.5 space-y-2">
                <div>
                    <div className="text-sm font-bold text-gray-900 dark:text-slate-100 truncate" title={jobName}>{jobName}</div>
                    <div className="text-xs text-gray-600 dark:text-slate-400 truncate" title={description}>{description}</div>
                </div>

                {/* Banana code (urgency) */}
                <div className="flex items-center justify-center py-1">
                    <StageIconRow stage={stage} iconSize={iconSize} />
                </div>

                {/* Date pair */}
                <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="rounded bg-gray-50 dark:bg-slate-700/50 px-2 py-1">
                        <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-slate-400">Start Install</div>
                        <div className="font-semibold text-gray-900 dark:text-slate-100">{startInstall || '—'}</div>
                    </div>
                    <div className="rounded bg-gray-50 dark:bg-slate-700/50 px-2 py-1">
                        <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-slate-400">Comp ETA</div>
                        <div className="font-semibold text-gray-900 dark:text-slate-100">{compEta || '—'}</div>
                    </div>
                </div>

                {/* Footer chips — fixed-position row so it stays aligned across cards regardless of notes length */}
                <div className="flex items-center gap-1.5 flex-wrap pt-1">
                    {progressChip(job['Job Comp'], 'Install')}
                    {progressChip(job['Invoiced'], 'Invoiced')}
                    {(job['Fab Hrs'] || job['Install HRS']) && (
                        <span
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-slate-200 border border-gray-300 dark:border-slate-600"
                            title="Fab / Install hours"
                        >
                            <span className="opacity-70">Hrs</span>
                            <span>{fmtHrs(job['Fab Hrs'])} / {fmtHrs(job['Install HRS'])}</span>
                        </span>
                    )}
                    <span className="ml-auto text-[10px] text-gray-400 dark:text-slate-500 group-hover:text-accent-500 dark:group-hover:text-accent-400">
                        Tap for details →
                    </span>
                </div>

                {/* Notes — kept at the very bottom so cards with notes only grow downward and the chip row stays aligned across the grid row */}
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
