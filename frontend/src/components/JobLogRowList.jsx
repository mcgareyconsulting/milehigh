/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Vertical list of JobLogRow components for the iPad/touch view of Job Log. Replaces the prior card-grid layout with dense, collapsible rows that embed JobsTableRow for full editing parity.
 * exports:
 *   default JobLogRowList: Props — jobs, secondaryResults, search, jumpToTarget, columns, formatCellValue, formatDate, onUpdate, onCascadeRecalculating, stageToGroup, stageGroupColors, stageGroupDupColors, isAdmin, isDrafter, onDelete, tableScrollRef, duplicateFabOrders, hasJobsData.
 * imports_from: [react, ./JobLogRow]
 * imported_by: [frontend/src/pages/JobLog.jsx]
 */
import React, { useRef, useState } from 'react';
import JobLogRow from './JobLogRow';
import { AsapDividerLabel, ASAP_DIVIDER_BOX_CLASS } from './AsapPropagationTag';

export default function JobLogRowList({
    jobs,
    secondaryResults = [],
    search = '',
    jumpToTarget = null,
    columns,
    formatCellValue,
    formatDate,
    onUpdate,
    onCascadeRecalculating,
    stageToGroup,
    stageGroupColors,
    stageGroupDupColors = null,
    isAdmin = false,
    isDrafter = false,
    onDelete = null,
    duplicateFabOrders = null,
    hasJobsData = false,
}) {
    const scrollRef = useRef(null);

    // Expand-all / Collapse-all: a fresh-identity signal object drives every JobLogRow;
    // `allExpanded` only tracks what the next button press should do.
    const [allExpanded, setAllExpanded] = useState(false);
    const [expandSignal, setExpandSignal] = useState(null);
    const toggleAll = () => {
        const next = !allExpanded;
        setAllExpanded(next);
        setExpandSignal({ value: next });
    };

    const showSecondary = jobs.length === 0 && hasJobsData && search.trim() !== '' && secondaryResults.length > 0;
    const isEmpty = jobs.length === 0 && !showSecondary;

    const isHighlightedRow = (row) =>
        jumpToTarget && String(row['Job #']) === jumpToTarget.job && String(row['Release #']) === jumpToTarget.release;

    const rowsToRender = jobs.length === 0 ? secondaryResults : jobs;

    return (
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-auto">
            {!isEmpty && (
                <div className="sticky top-0 z-10 flex items-center justify-end px-3 py-1.5 bg-gray-100 dark:bg-slate-700 border-b border-gray-200 dark:border-slate-600">
                    <button
                        type="button"
                        onClick={toggleAll}
                        className="inline-flex items-center gap-1 px-2 py-1 text-xs font-semibold text-gray-700 dark:text-slate-200 rounded hover:bg-gray-200 dark:hover:bg-slate-600 transition-colors"
                        title={allExpanded ? 'Collapse every row' : 'Expand every row'}
                    >
                        <span className={`inline-block transition-transform ${allExpanded ? 'rotate-90' : ''}`} aria-hidden="true">▸</span>
                        {allExpanded ? 'Collapse all' : 'Expand all'}
                    </button>
                </div>
            )}

            {showSecondary && (
                <div className="m-2 px-4 py-3 rounded-lg bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 text-sm font-medium">
                    <span className="mr-2">⚠️</span>
                    {`'${search.trim()}' not found under current filters. Showing results from unfiltered search:`}
                </div>
            )}

            {isEmpty ? (
                <div className="flex items-center justify-center py-16 text-center text-gray-500 dark:text-slate-400 font-medium">
                    {hasJobsData ? 'No records match the selected filters.' : 'No records found.'}
                </div>
            ) : (
                <div>
                    {rowsToRender.map((row, index) => (
                        row._asapDivider ? (
                            <div
                                key={row.id}
                                className={`${ASAP_DIVIDER_BOX_CLASS} border-y`}
                            >
                                <AsapDividerLabel count={row._asapCount} />
                            </div>
                        ) : (
                        <JobLogRow
                            key={row.id}
                            job={row}
                            columns={columns}
                            formatCellValue={formatCellValue}
                            formatDate={formatDate}
                            rowIndex={index}
                            onUpdate={onUpdate}
                            onCascadeRecalculating={onCascadeRecalculating}
                            stageToGroup={stageToGroup}
                            stageGroupColors={stageGroupColors}
                            stageGroupDupColors={stageGroupDupColors}
                            isJumpToHighlight={isHighlightedRow(row)}
                            isAdmin={isAdmin}
                            isDrafter={isDrafter}
                            onDelete={onDelete}
                            tableScrollRef={scrollRef}
                            duplicateFabOrders={duplicateFabOrders}
                            expandSignal={expandSignal}
                        />
                        )
                    ))}
                </div>
            )}
        </div>
    );
}
