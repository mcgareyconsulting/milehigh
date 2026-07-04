/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Dense row rendering a single job release for the iPad/touch view of Job Log. Critical fields are visible by default using clean, table-free editors (Release # link, Stage pill, Fab Order input, Start install pill); the chevron expands to embed the desktop JobsTableRow for full editing parity on the remaining columns.
 * exports:
 *   default JobLogRow: Props — job, columns, formatCellValue, formatDate, rowIndex, onUpdate, onCascadeRecalculating, stageToGroup, stageGroupColors, stageGroupDupColors, isJumpToHighlight, isAdmin, isDrafter, onDelete, tableScrollRef, duplicateFabOrders.
 * imports_from: [react, ./JobsTableRow, ./ReleaseNumberLink, ./StageEditor, ./FabOrderEditor, ./StartInstallEditor, ../utils/stageProgress, ../utils/formatters]
 * imported_by: [frontend/src/components/JobLogRowList.jsx]
 * invariants:
 *   - Critical (collapsed) fields: Job # / Release #, Job name + Description subtext, Fab Order (editable), Stage (editable), Start install, Comp. ETA (read-only). None embed JobsTableRow — each is a self-contained editor that writes via jobsApi and refetches through onUpdate (so the backend Complete-zone cascade is reflected). Everything else (hours, Released, BY, Notes, …) lives in the expansion.
 *   - Release # opens the FC drawing: version-history hub for drafters/admins, latest markup (view) or Procore link otherwise.
 *   - Expanded section embeds JobsTableRow restricted to the remaining columns (showActions={false}); those edit handlers route through the same JobsTableRow APIs as the desktop table.
 */
import React, { useState, useEffect } from 'react';
import { JobsTableRow } from './JobsTableRow';
import StartInstallEditor from './StartInstallEditor';
import ReleaseNumberLink from './ReleaseNumberLink';
import StageEditor from './StageEditor';
import FabOrderEditor from './FabOrderEditor';
import { ASAP_PROPAGATED_ROW_CLASS } from './AsapPropagationTag';
import { isCompleteStage } from '../utils/stageProgress';
import { formatDateShort } from '../utils/formatters';

const fmt = (v) => (v == null || v === '' ? '—' : String(v));

const CRITICAL_COLUMNS = new Set([
    'Job #',
    'Release #',
    'Job',
    'Description',
    'Stage',
    'Fab Order',
    'Start install',
    'Comp. ETA',
]);

export default function JobLogRow({
    job,
    columns,
    formatCellValue,
    formatDate = formatDateShort,
    rowIndex = 0,
    onUpdate,
    onCascadeRecalculating,
    stageToGroup,
    stageGroupColors,
    stageGroupDupColors = null,
    isJumpToHighlight = false,
    isAdmin = false,
    isDrafter = false,
    onDelete = null,
    tableScrollRef = null,
    duplicateFabOrders = null,
    expandSignal = null,
}) {
    const [expanded, setExpanded] = useState(false);

    // Expand-all / Collapse-all: the list bumps expandSignal (fresh identity each
    // click) to drive every row; individual chevron toggles still work afterward.
    useEffect(() => {
        if (expandSignal) setExpanded(expandSignal.value);
    }, [expandSignal]);

    const jobNum = fmt(job['Job #']);
    const jobName = fmt(job['Job']);
    const description = (job['Description'] || '').toString().trim();
    const stage = job['Stage'] || 'Released';
    const complete = isCompleteStage(stage);

    const expandedColumns = (columns || []).filter((c) => !CRITICAL_COLUMNS.has(c));

    const sharedRowProps = {
        row: job,
        formatCellValue,
        formatDate,
        rowIndex,
        onDragStart: () => {},
        onDragOver: () => {},
        onDragLeave: () => {},
        onDrop: () => {},
        isDragging: null,
        dragOverIndex: null,
        onUpdate,
        onCascadeRecalculating,
        stageToGroup,
        stageGroupColors,
        stageGroupDupColors,
        isJumpToHighlight: false,
        isAdmin: false,
        isDrafter,
        onDelete: null,
        tableScrollRef,
        duplicateFabOrders,
    };

    // Row background mirrors the desktop table (JobsTableRow — keep in sync): complete rows
    // are muted + receding (pale slab in light, DARKER than active rows in dark), otherwise
    // alternate white / blue. Jump-to highlight wins over the base tone.
    const rowBgClass = isJumpToHighlight
        ? 'bg-amber-50 dark:bg-amber-900/20'
        : complete
            ? 'bg-gray-200 dark:bg-slate-950'
            : (rowIndex % 2 === 0 ? 'bg-white dark:bg-slate-800' : 'bg-blue-300 dark:bg-slate-600');
    // Complete rows dim their primary text to recede alongside the muted slab.
    const primaryTextClass = complete
        ? 'text-gray-600 dark:text-slate-400'
        : 'text-gray-900 dark:text-slate-100';

    // Collapsed rows read as a tight list (bottom border only). Expanded rows lift
    // into a distinct card — margin + border + shadow — so adjacent open cards
    // separate cleanly in the Expand-all view.
    const containerCls = `${rowBgClass} ${job._asapPropagated ? ASAP_PROPAGATED_ROW_CLASS : ''} ${
        expanded
            ? 'mx-2 my-2 rounded-lg border border-gray-300 dark:border-slate-600 shadow-sm overflow-hidden'
            : 'border-b border-gray-200 dark:border-slate-700'
    }`;

    const toggle = () => setExpanded((v) => !v);
    const handleKey = (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggle();
        }
    };

    return (
        <div className={containerCls}>
            {/* Collapsed row — outer is a div so embedded editors can receive focus/clicks without nesting issues */}
            <div
                role="button"
                tabIndex={0}
                aria-expanded={expanded}
                onClick={toggle}
                onKeyDown={handleKey}
                className="w-full flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-black/10 dark:hover:bg-white/15 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:ring-inset"
            >
                {/* Job # · Release # — single inline group so both share one baseline.
                    Release # opens the FC drawing / version hub; the rest toggles the row. */}
                <span className={`shrink-0 font-mono text-sm font-semibold ${primaryTextClass} whitespace-nowrap`}>
                    {jobNum}
                    <span className="text-gray-400 dark:text-slate-500"> · </span>
                    <ReleaseNumberLink
                        value={fmt(job['Release #'])}
                        releaseId={job.id}
                        jobReleaseLabel={`${jobNum}-${fmt(job['Release #'])}`}
                        hasDrawing={job.has_drawing}
                        viewerUrl={job.viewer_url}
                        canMarkup={isAdmin || isDrafter}
                    />
                </span>

                <span className={`flex-1 min-w-0 truncate text-sm ${primaryTextClass}`}>
                    <span className="font-semibold">{jobName}</span>
                    {description ? (
                        <span className="text-gray-500 dark:text-slate-400 ml-1">— {description}</span>
                    ) : null}
                </span>

                {/* Fab Order — left of Stage, matching the desktop table column order */}
                <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
                    <FabOrderEditor
                        row={job}
                        onUpdate={onUpdate}
                        stageToGroup={stageToGroup}
                        duplicateFabOrders={duplicateFabOrders}
                        stageGroupDupColors={stageGroupDupColors}
                    />
                </div>

                {/* Stage — colored pill backed by a native select (clean, never clipped) */}
                <div className="shrink-0">
                    <StageEditor
                        row={job}
                        onUpdate={onUpdate}
                        stageToGroup={stageToGroup}
                        stageGroupColors={stageGroupColors}
                    />
                </div>

                {/* Start install — colored ASAP / hard-date / formula pill */}
                <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
                    <StartInstallEditor row={job} onUpdate={onUpdate} formatDate={formatDate} variant="pill" />
                </div>

                {/* Comp. ETA — read-only date, sized to match the Start-install pill */}
                <span
                    className={`shrink-0 inline-flex items-center justify-center min-w-[72px] rounded px-2 py-0.5 text-xs font-semibold tabular-nums leading-none ${complete ? 'text-gray-500 dark:text-slate-500' : 'text-gray-700 dark:text-slate-300'}`}
                    title="Comp. ETA"
                >
                    <span className="mr-1 text-[9px] font-bold uppercase tracking-wide text-gray-400 dark:text-slate-500">ETA</span>
                    {formatDate(job['Comp. ETA']) || '—'}
                </span>

                <span
                    className={`shrink-0 inline-block transition-transform text-gray-500 dark:text-slate-400 ${expanded ? 'rotate-90' : ''}`}
                    aria-hidden="true"
                >
                    ▸
                </span>
            </div>

            {/* Expanded section — remaining columns with full editing */}
            {expanded && expandedColumns.length > 0 && (
                <div className="border-t border-gray-300 dark:border-slate-600 overflow-x-auto">
                    <table className="w-full" style={{ borderCollapse: 'collapse' }}>
                        <thead>
                            <tr>
                                {expandedColumns.map((col) => (
                                    <th
                                        key={col}
                                        className="px-1 py-1 text-[10px] font-bold uppercase tracking-wide text-gray-700 dark:text-slate-300 border border-gray-400 dark:border-slate-500 whitespace-nowrap"
                                    >
                                        {col}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            <JobsTableRow
                                {...sharedRowProps}
                                columns={expandedColumns}
                                isAdmin={isAdmin}
                                onDelete={onDelete}
                                showActions={false}
                            />
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
