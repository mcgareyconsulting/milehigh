/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Dense, table-like row rendering a single job release for the iPad/touch view of Job Log. Critical fields visible by default (with inline Stage and Fab Order editors); chevron expands to embed the desktop JobsTableRow for full editing parity on the remaining columns.
 * exports:
 *   default JobLogRow: Props — job, columns, formatCellValue, formatDate, rowIndex, onUpdate, onCascadeRecalculating, stageToGroup, stageGroupColors, stageGroupDupColors, isJumpToHighlight, isAdmin, isDrafter, onDelete, tableScrollRef, duplicateFabOrders.
 * imports_from: [react, ./JobsTableRow, ../utils/stageProgress, ../utils/formatters]
 * imported_by: [frontend/src/components/JobLogRowList.jsx]
 * invariants:
 *   - Critical (collapsed) fields: Job # / Release #, Job name + Description subtext, Stage (editable), Fab Order (editable), Start install.
 *   - Stage + Fab Order editors are rendered by embedding JobsTableRow with a single-column subset so cascade logic (Complete → clear job_comp/fab_order, etc.) remains intact.
 *   - Expanded section embeds JobsTableRow restricted to the remaining columns. All edit handlers route through the same JobsTableRow APIs as the desktop table.
 */
import React, { useState } from 'react';
import { JobsTableRow } from './JobsTableRow';
import StartInstallEditor from './StartInstallEditor';
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
]);

function InlineCell({ children }) {
    return (
        <div onClick={(e) => e.stopPropagation()} className="shrink-0">
            <table className="inline-table" style={{ borderCollapse: 'collapse' }}>
                <tbody>{children}</tbody>
            </table>
        </div>
    );
}

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
}) {
    const [expanded, setExpanded] = useState(false);

    const jobNum = fmt(job['Job #']);
    const release = fmt(job['Release #']);
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

    const containerCls = `border-b border-gray-200 dark:border-slate-700 ${
        isJumpToHighlight ? 'bg-amber-50 dark:bg-amber-900/20' : ''
    } ${complete ? 'opacity-90' : ''}`;

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
                className="w-full flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-gray-50 dark:hover:bg-slate-700/60 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:ring-inset"
            >
                <span className="shrink-0 font-mono text-sm font-semibold text-gray-900 dark:text-slate-100">
                    {jobNum}<span className="text-gray-400 dark:text-slate-500">·</span>{release}
                </span>

                <span className="flex-1 min-w-0 truncate text-sm text-gray-900 dark:text-slate-100">
                    <span className="font-semibold">{jobName}</span>
                    {description ? (
                        <span className="text-gray-500 dark:text-slate-400 ml-1">— {description}</span>
                    ) : null}
                </span>

                {/* Inline Stage editor */}
                <InlineCell>
                    <JobsTableRow {...sharedRowProps} columns={['Stage']} compact />
                </InlineCell>

                {/* Inline Fab Order editor */}
                <InlineCell>
                    <JobsTableRow {...sharedRowProps} columns={['Fab Order']} compact />
                </InlineCell>

                <span className="shrink-0" onClick={(e) => e.stopPropagation()}>
                    <StartInstallEditor row={job} onUpdate={onUpdate} formatDate={formatDate} variant="pill" />
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
                <div className="bg-gray-50 dark:bg-slate-800/60 border-t border-gray-200 dark:border-slate-700 overflow-x-auto">
                    <table className="w-full" style={{ borderCollapse: 'collapse' }}>
                        <thead>
                            <tr>
                                {expandedColumns.map((col) => (
                                    <th
                                        key={col}
                                        className="px-1 py-1 text-[10px] font-bold uppercase tracking-wide text-gray-600 dark:text-slate-400 bg-gray-100 dark:bg-slate-700/80 border-r border-gray-200 dark:border-slate-600 whitespace-nowrap"
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
                            />
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
