/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Responsive card grid for Job Log and Archive — renders JobLogCard tiles, the secondary-search amber banner, and an empty state.
 * exports:
 *   default JobLogCardGrid: Props — jobs, secondaryResults (optional), search, jumpToTarget, stageToGroup, stageGroupColors, stageGroupDupColors, duplicateFabOrders, isHighlightedRow, hasJobsData, onUpdate (refetch after a card edit), layout ('grid' | 'column'), isAdmin, isDrafter (drawing-hub markup access on cards).
 * imports_from: [react, ./JobLogCard, ./JobDetailsModal]
 * imported_by: [frontend/src/pages/JobLogContent.jsx, frontend/src/pages/Archive.jsx]
 * invariants:
 *   - Tap on a card opens JobDetailsModal locally (no parent state required).
 *   - layout='grid' (Archive): 1 col on phone, 2 col on iPad, 3 col on 27", 4 col on 3xl.
 *   - layout='column' (Job Log Cards view): ONE centered column — deliberate Kanban-feed look
 *     with no left/right position ambiguity (top-to-bottom = the sorted list order), cards
 *     floating on a muted backdrop. Used on phones + portrait tablets (enforced) and wherever
 *     the ViewToggle picks Cards.
 */
import React, { useState } from 'react';
import JobLogCard from './JobLogCard';
import { JobDetailsModal } from './JobDetailsModal';
import { AsapDividerLabel, ASAP_DIVIDER_BOX_CLASS } from './AsapPropagationTag';

export default function JobLogCardGrid({
    jobs,
    secondaryResults = [],
    search = '',
    jumpToTarget = null,
    stageToGroup,
    stageGroupColors,
    stageGroupDupColors = null,
    duplicateFabOrders = null,
    hasJobsData = false,
    onUpdate = null,
    layout = 'grid',
    isAdmin = false,
    isDrafter = false,
}) {
    const [selectedJob, setSelectedJob] = useState(null);

    const showSecondary = jobs.length === 0 && hasJobsData && search.trim() !== '' && secondaryResults.length > 0;
    const isEmpty = jobs.length === 0 && !showSecondary;

    const isHighlightedRow = (row) =>
        jumpToTarget && String(row['Job #']) === jumpToTarget.job && String(row['Release #']) === jumpToTarget.release;

    const isColumn = layout === 'column';

    return (
        <div className={`flex-1 min-h-0 overflow-auto p-2 sm:p-3 3xl:p-5 ${isColumn ? 'rounded-xl bg-gray-100/80 dark:bg-slate-900/50' : ''}`}>
            {showSecondary && (
                <div className="mb-3 px-4 py-3 rounded-lg bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 text-sm font-medium">
                    <span className="mr-2">⚠️</span>
                    {`'${search.trim()}' not found under current filters. Showing results from unfiltered search:`}
                </div>
            )}

            {isEmpty ? (
                <div className="flex items-center justify-center py-16 text-center text-gray-500 dark:text-slate-400 font-medium">
                    {hasJobsData ? 'No records match the selected filters.' : 'No records found.'}
                </div>
            ) : (
                <div className={isColumn
                    ? 'flex flex-col gap-2 max-w-3xl mx-auto w-full'
                    : 'grid gap-3 sm:gap-4 grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 3xl:grid-cols-4'}>
                    {(jobs.length === 0 ? secondaryResults : jobs).map((row, index) => (
                        row._asapDivider ? (
                            <div
                                key={row.id}
                                className={`${ASAP_DIVIDER_BOX_CLASS} border rounded-lg col-span-full`}
                            >
                                <AsapDividerLabel count={row._asapCount} />
                            </div>
                        ) : (
                        <JobLogCard
                            key={row.id}
                            job={row}
                            onOpen={setSelectedJob}
                            onUpdate={onUpdate}
                            stageToGroup={stageToGroup}
                            stageGroupColors={stageGroupColors}
                            stageGroupDupColors={stageGroupDupColors}
                            duplicateFabOrders={duplicateFabOrders}
                            isHighlighted={isHighlightedRow(row)}
                            isAdmin={isAdmin}
                            isDrafter={isDrafter}
                            rowIndex={index}
                            banded={isColumn}
                        />
                        )
                    ))}
                </div>
            )}

            <JobDetailsModal
                isOpen={selectedJob != null}
                onClose={() => setSelectedJob(null)}
                job={selectedJob}
            />
        </div>
    );
}
