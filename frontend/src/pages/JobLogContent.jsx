/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Table/cards content for the Job Log (Table view). Renders the filtered releases provided by the persistent ReleasesLayout via Outlet context — device breakpoint picks the mobile card / tablet card / desktop table layout. Holds only table-render-local state (scroll ref, disabled drag stubs).
 * exports:
 *   JobLogContent: Child route element for /job-log; consumes useOutletContext() from ReleasesLayout.
 * imports_from: [react, react-router-dom, ../components/ColumnHeaderFilter, ../components/JobsTableRow, ../components/StageIconRow, ../components/AsapPropagationTag, ../components/JobLogCardGrid, ../components/JobLogRowList, ../utils/formatters, ../utils/jobLogColumns, ../constants/columnHeaders]
 * imported_by: [../App.jsx]
 * invariants:
 *   - All filter state + filtered rows come from ReleasesLayout via context; this component never calls useJobsFilters.
 *   - Column-header dropdown UI renders here but mutates layout state via setColumnFilter/setColumnSort from context (the reactive loop recomputes displayJobs/uniqueValuesByColumn upstream).
 *   - effectiveView (mobilecard/cards/table) is device-driven and orthogonal to the Table/Board/Timeline switch.
 */
import React, { useRef } from 'react';
import { useOutletContext } from 'react-router-dom';
import ColumnHeaderFilter from '../components/ColumnHeaderFilter';
import { JobsTableRow } from '../components/JobsTableRow';
import { BananaCodeHeader } from '../components/StageIconRow';
import { AsapDividerLabel, ASAP_DIVIDER_BOX_CLASS } from '../components/AsapPropagationTag';
import JobLogCardGrid from '../components/JobLogCardGrid';
import JobLogRowList from '../components/JobLogRowList';
import { formatDateShort, formatCellValue } from '../utils/formatters';
import { FILTERABLE_COLUMNS, DATE_COLUMNS } from '../utils/jobLogColumns';
import { HEADER_OVERRIDES } from '../constants/columnHeaders';

function JobLogContent() {
    const {
        loading,
        fetchError,
        effectiveView,
        renderRows,
        secondarySearchResults,
        search,
        jumpToTarget,
        stageToGroup,
        stageGroupColors,
        stageGroupDupColors,
        duplicateFabOrders,
        hasJobsData,
        refetch,
        handleCascadeRecalculating,
        columnHeaders,
        columnWidthPercents,
        uniqueValuesByColumn,
        columnFilters,
        columnSort,
        setColumnFilter,
        setColumnSort,
        isAdmin,
        isDrafter,
        isOldMan,
        handleDeleteJob,
    } = useOutletContext();

    const tableScrollRef = useRef(null);

    // Drag-and-drop reorder is disabled — keep no-op handlers so JobsTableRow's props stay satisfied.
    const draggedIndex = null;
    const dragOverIndex = null;
    const handleDragStart = () => { };
    const handleDragOver = () => { };
    const handleDragLeave = () => { };
    const handleDrop = () => { };

    const tableColumnCount = columnHeaders.length;

    return (
        <>
            {loading && (
                <div className="text-center py-12">
                    <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                    <p className="text-gray-600 font-medium">Loading Jobs data...</p>
                </div>
            )}

            {fetchError && !loading && (
                <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-6 py-4 rounded-lg shadow-sm">
                    <div className="flex items-start">
                        <span className="text-xl mr-3">⚠️</span>
                        <div>
                            <p className="font-semibold">Unable to load Jobs data</p>
                            <p className="text-sm mt-1">{fetchError}</p>
                        </div>
                    </div>
                </div>
            )}

            {!loading && !fetchError && effectiveView === 'mobilecard' && (
                <JobLogCardGrid
                    jobs={renderRows}
                    secondaryResults={secondarySearchResults}
                    search={search}
                    jumpToTarget={jumpToTarget}
                    stageToGroup={stageToGroup}
                    stageGroupColors={stageGroupColors}
                    stageGroupDupColors={stageGroupDupColors}
                    duplicateFabOrders={duplicateFabOrders}
                    hasJobsData={hasJobsData}
                    onUpdate={() => refetch(true)}
                />
            )}

            {!loading && !fetchError && effectiveView === 'cards' && (
                <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-xl shadow-sm overflow-hidden flex-1 min-h-0 flex flex-col">
                    <JobLogRowList
                        jobs={renderRows}
                        secondaryResults={secondarySearchResults}
                        search={search}
                        jumpToTarget={jumpToTarget}
                        columns={columnHeaders}
                        formatCellValue={formatCellValue}
                        formatDate={formatDateShort}
                        onUpdate={() => refetch(true)}
                        onCascadeRecalculating={handleCascadeRecalculating}
                        stageToGroup={stageToGroup}
                        stageGroupColors={stageGroupColors}
                        stageGroupDupColors={stageGroupDupColors}
                        isAdmin={isAdmin}
                        isDrafter={isDrafter}
                        onDelete={handleDeleteJob}
                        duplicateFabOrders={duplicateFabOrders}
                        hasJobsData={hasJobsData}
                    />
                </div>
            )}

            {!loading && !fetchError && effectiveView === 'table' && (
                <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-xl shadow-sm overflow-hidden flex-1 min-h-0 flex flex-col">
                    <div
                        ref={tableScrollRef}
                        className="job-log-table-scroll overflow-auto flex-1"
                    >
                        <table className="w-full" style={{ borderCollapse: 'collapse', tableLayout: 'fixed', width: '100%' }}>
                            <thead className="sticky top-0 z-10">
                                <tr>
                                    {columnHeaders.map((column) => {
                                        const isReleaseNumber = column === 'Release #';
                                        const displayHeader = HEADER_OVERRIDES[column] ?? column;
                                        const colWidthPct = columnWidthPercents[column];
                                        const isFilterable = FILTERABLE_COLUMNS.has(column);
                                        const colInfo = isFilterable ? uniqueValuesByColumn[column] : null;
                                        const colSelected = columnFilters[column] ?? [];
                                        const isUrgency = column === 'Urgency';
                                        return (
                                            <th
                                                key={column}
                                                className={`${isReleaseNumber ? 'px-1' : 'px-2'} ${isOldMan ? 'py-2 text-[13px]' : 'py-0.5 text-[11px]'} align-middle text-center font-bold text-gray-700 dark:text-slate-200 bg-gray-100 dark:bg-slate-700 border-r border-b-2 border-gray-400 dark:border-slate-500`}
                                                style={colWidthPct != null ? { width: `${colWidthPct}%` } : undefined}
                                            >
                                                {isUrgency ? (
                                                    <BananaCodeHeader />
                                                ) : isFilterable ? (
                                                    <ColumnHeaderFilter
                                                        column={column}
                                                        values={colInfo?.values ?? []}
                                                        hasBlanks={colInfo?.hasBlanks ?? false}
                                                        selected={new Set(colSelected)}
                                                        onChange={(next) => setColumnFilter(column, [...next])}
                                                        sort={columnSort}
                                                        onSort={(dir) => setColumnSort(column, dir)}
                                                        isActive={colSelected.length > 0}
                                                        sortLabels={DATE_COLUMNS.has(column)
                                                            ? { asc: 'Oldest → Newest', desc: 'Newest → Oldest' }
                                                            : undefined}
                                                    >
                                                        {displayHeader}
                                                    </ColumnHeaderFilter>
                                                ) : (
                                                    displayHeader
                                                )}
                                            </th>
                                        );
                                    })}
                                    {isAdmin && (
                                        <th className="px-1 py-0.5 text-center text-xl font-bold text-gray-700 dark:text-slate-200 uppercase tracking-wider bg-gray-100 dark:bg-slate-700 border-r border-b-2 border-gray-400 dark:border-slate-500 w-8">
                                            ⚙
                                        </th>
                                    )}
                                </tr>
                            </thead>
                            <tbody>
                                {renderRows.length === 0 ? (
                                    hasJobsData && search.trim() !== '' && secondarySearchResults.length > 0 ? (
                                        <>
                                            <tr>
                                                <td
                                                    colSpan={tableColumnCount + (isAdmin ? 1 : 0)}
                                                    className="px-6 py-6 text-center text-amber-800 dark:text-amber-200 font-medium bg-amber-50 dark:bg-amber-900/30 border-b border-amber-200 dark:border-amber-800"
                                                >
                                                    <span className="mr-2">⚠️</span>
                                                    {`'${search.trim()}' not found under current filters. Showing results from unfiltered search:`}
                                                </td>
                                            </tr>
                                            {secondarySearchResults.map((row, index) => (
                                                <JobsTableRow
                                                    key={row.id}
                                                    row={row}
                                                    columns={columnHeaders}
                                                    isJumpToHighlight={jumpToTarget && String(row['Job #']) === jumpToTarget.job && String(row['Release #']) === jumpToTarget.release}
                                                    formatCellValue={formatCellValue}
                                                    formatDate={formatDateShort}
                                                    rowIndex={index}
                                                    onDragStart={handleDragStart}
                                                    onDragOver={handleDragOver}
                                                    onDragLeave={handleDragLeave}
                                                    onDrop={handleDrop}
                                                    isDragging={draggedIndex}
                                                    dragOverIndex={dragOverIndex}
                                                    onUpdate={() => refetch(true)}
                                                    onCascadeRecalculating={handleCascadeRecalculating}
                                                    stageToGroup={stageToGroup}
                                                    stageGroupColors={stageGroupColors}
                                                    stageGroupDupColors={stageGroupDupColors}
                                                    isAdmin={isAdmin}
                                                    isDrafter={isDrafter}
                                                    onDelete={handleDeleteJob}
                                                    tableScrollRef={tableScrollRef}
                                                    duplicateFabOrders={duplicateFabOrders}
                                                />
                                            ))}
                                        </>
                                    ) : (
                                        <tr>
                                            <td
                                                colSpan={tableColumnCount + (isAdmin ? 1 : 0)}
                                                className="px-6 py-12 text-center text-gray-500 dark:text-slate-400 font-medium bg-white dark:bg-slate-800 rounded-md"
                                            >
                                                {hasJobsData
                                                    ? 'No records match the selected filters.'
                                                    : 'No records found.'
                                                }
                                            </td>
                                        </tr>
                                    )
                                ) : (
                                    renderRows.map((row, index) => (
                                        row._asapDivider ? (
                                            <tr key={row.id}>
                                                <td
                                                    colSpan={tableColumnCount + (isAdmin ? 1 : 0)}
                                                    className={`${ASAP_DIVIDER_BOX_CLASS} border-y`}
                                                >
                                                    <AsapDividerLabel count={row._asapCount} />
                                                </td>
                                            </tr>
                                        ) : (
                                        <JobsTableRow
                                            key={row.id}
                                            row={row}
                                            columns={columnHeaders}
                                            isJumpToHighlight={jumpToTarget && String(row['Job #']) === jumpToTarget.job && String(row['Release #']) === jumpToTarget.release}
                                            formatCellValue={formatCellValue}
                                            formatDate={formatDateShort}
                                            rowIndex={index}
                                            onDragStart={handleDragStart}
                                            onDragOver={handleDragOver}
                                            onDragLeave={handleDragLeave}
                                            onDrop={handleDrop}
                                            isDragging={draggedIndex}
                                            dragOverIndex={dragOverIndex}
                                            onUpdate={() => refetch(true)}
                                            onCascadeRecalculating={handleCascadeRecalculating}
                                            stageToGroup={stageToGroup}
                                            stageGroupColors={stageGroupColors}
                                            stageGroupDupColors={stageGroupDupColors}
                                            isAdmin={isAdmin}
                                            isDrafter={isDrafter}
                                            onDelete={handleDeleteJob}
                                            tableScrollRef={tableScrollRef}
                                            duplicateFabOrders={duplicateFabOrders}
                                        />
                                        )
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </>
    );
}

export default JobLogContent;
