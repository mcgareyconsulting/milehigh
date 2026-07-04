/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Table/cards content for the Job Log (Table view). Renders the filtered releases provided by the persistent ReleasesLayout via Outlet context — device breakpoint picks the mobile card / tablet card / desktop table layout. Holds only table-render-local state (scroll ref, disabled drag stubs).
 * exports:
 *   JobLogContent: Child route element for /job-log; consumes useOutletContext() from ReleasesLayout.
 * imports_from: [react, react-router-dom, ../components/ColumnHeaderFilter, ../components/JobsTableRow, ../components/StageIconRow, ../components/AsapPropagationTag, ../components/JobLogCardGrid, ../utils/formatters, ../utils/jobLogColumns, ../constants/columnHeaders]
 * imported_by: [../App.jsx]
 * invariants:
 *   - All filter state + filtered rows come from ReleasesLayout via context; this component never calls useJobsFilters.
 *   - Column-header dropdown UI renders here but mutates layout state via setColumnFilter/setColumnSort from context (the reactive loop recomputes displayJobs/uniqueValuesByColumn upstream).
 *   - effectiveView (mobilecard/cards/table) is device-driven and orthogonal to the Table/Board/Timeline switch.
 */
import React, { useRef, useMemo, useState, useEffect } from 'react';
import { useOutletContext, useLocation, useNavigate } from 'react-router-dom';
import ColumnHeaderFilter from '../components/ColumnHeaderFilter';
import { JobsTableRow } from '../components/JobsTableRow';
import { PdfVersionHistoryModal } from '../components/PdfVersionHistoryModal';
import { PdfMarkupModal } from '../components/PdfMarkupModal';
import { BananaCodeHeader } from '../components/StageIconRow';
import { AsapDividerLabel, ASAP_DIVIDER_BOX_CLASS } from '../components/AsapPropagationTag';
import JobLogCardGrid from '../components/JobLogCardGrid';
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
        isDesktop,
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

    // Open the drawing hub directly when arriving from a drawing-comment notification.
    const location = useLocation();
    const navigate = useNavigate();
    const [drawingModal, setDrawingModal] = useState(null); // { releaseId, versionId, jobReleaseLabel }
    // Markup modal opened from the notification-driven attachments hub (View/Edit a
    // version). Mirrors the wiring in JobsTableRow / History so View/Edit works here too.
    const [pdfMarkupOpen, setPdfMarkupOpen] = useState(false);
    const [pdfMarkupVersionId, setPdfMarkupVersionId] = useState(null);
    const [pdfMarkupMode, setPdfMarkupMode] = useState('view');
    const [pdfMarkupReleaseId, setPdfMarkupReleaseId] = useState(null);

    useEffect(() => {
        const od = location.state?.openDrawing;
        if (od?.releaseId) {
            setDrawingModal(od);
            // Clear nav state so a refresh or back-navigation doesn't reopen the modal.
            navigate(location.pathname, { replace: true, state: null });
        }
    }, [location.state, location.pathname, navigate]);

    // On iPad/narrow widths the full table doesn't fit in landscape, so drop the two
    // lowest-frequency columns (BY, Released) plus the wide Urgency/Banana Code column
    // and re-normalize the remaining widths to 100% (fixed-layout table). Desktop keeps
    // every column; CSV/PDF export are unaffected (they read the full columnHeaders from
    // ReleasesLayout).
    const { tableColumns, tableWidthPercents } = useMemo(() => {
        if (isDesktop) return { tableColumns: columnHeaders, tableWidthPercents: columnWidthPercents };
        const NARROW_HIDDEN = new Set(['BY', 'Released', 'Urgency']);
        const cols = columnHeaders.filter((c) => !NARROW_HIDDEN.has(c));
        const sum = cols.reduce((acc, c) => acc + (columnWidthPercents[c] ?? 0), 0) || 1;
        const widths = Object.fromEntries(cols.map((c) => [c, ((columnWidthPercents[c] ?? 0) / sum) * 100]));
        return { tableColumns: cols, tableWidthPercents: widths };
    }, [isDesktop, columnHeaders, columnWidthPercents]);

    // The admin row-actions column (⚙ edit/delete) is desktop-only (14"+ screens) — no
    // exposure on tablet/mobile. Gates the header cell, the per-row actions, and the
    // empty/divider colSpan math so the table stays aligned. Admin cell-editing is unaffected.
    const showAdminActions = isAdmin && isDesktop;

    // Drag-and-drop reorder is disabled — keep no-op handlers so JobsTableRow's props stay satisfied.
    const draggedIndex = null;
    const dragOverIndex = null;
    const handleDragStart = () => { };
    const handleDragOver = () => { };
    const handleDragLeave = () => { };
    const handleDrop = () => { };

    const tableColumnCount = tableColumns.length;

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

            {/* Cards = single-column Kanban-style feed (JobLogCard) everywhere cards show:
                phones + portrait tablets (enforced) and Cards-toggled landscape/desktop.
                Replaced the old dense expandable-row list (JobLogRowList), which read as
                "the table but slightly different" rather than a genuinely distinct view. */}
            {!loading && !fetchError && (effectiveView === 'mobilecard' || effectiveView === 'cards') && (
                <JobLogCardGrid
                    layout="column"
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
                    isAdmin={isAdmin}
                    isDrafter={isDrafter}
                />
            )}

            {!loading && !fetchError && effectiveView === 'table' && (
                // Outer frame uses the same translucent ink as the grid dividers so the
                // table edge reads as part of the lattice, not a separate lighter band.
                <div className="bg-white dark:bg-slate-800 border border-black/[0.18] dark:border-white/[0.12] rounded-xl shadow-sm overflow-hidden flex-1 min-h-0 flex flex-col">
                    <div
                        ref={tableScrollRef}
                        className="job-log-table-scroll overflow-auto flex-1"
                    >
                        <table className="w-full" style={{ borderCollapse: 'collapse', tableLayout: 'fixed', width: '100%' }}>
                            <thead className="sticky top-0 z-10">
                                <tr>
                                    {tableColumns.map((column) => {
                                        const isReleaseNumber = column === 'Release #';
                                        const displayHeader = HEADER_OVERRIDES[column] ?? column;
                                        const colWidthPct = tableWidthPercents[column];
                                        const isFilterable = FILTERABLE_COLUMNS.has(column);
                                        const colInfo = isFilterable ? uniqueValuesByColumn[column] : null;
                                        const colSelected = columnFilters[column] ?? [];
                                        const isUrgency = column === 'Urgency';
                                        // Last visible column (no trailing gear column) gets no vertical divider,
                                        // just the thin bottom rule shared by every header cell. Both dividers use
                                        // box-shadow, not a real border, so the vertical one lines up pixel-for-pixel
                                        // with the body cells' own box-shadow dividers (a real border under
                                        // border-collapse is centered on the shared boundary and drifts a sub-pixel
                                        // from a non-collapsed element) — and box-shadow is also immune to Safari's
                                        // bug where collapsed borders on sticky <th> cells fail to paint.
                                        const isLastHeaderColumn = tableColumns[tableColumns.length - 1] === column && !showAdminActions;
                                        // Same translucent ink as the body cells (JobsTableRow — keep in sync):
                                        // black 18% / white 12%. The bottom rule is the one place the ink doubles
                                        // (~2× alpha) so the header reads as an anchored band without introducing
                                        // a second line style.
                                        const headerDividerShadow = isLastHeaderColumn
                                            ? 'shadow-[inset_0_-1px_0_0_#0000005c] dark:shadow-[inset_0_-1px_0_0_#ffffff3d]'
                                            : 'shadow-[inset_-1px_0_0_0_#0000002e,inset_0_-1px_0_0_#0000005c] dark:shadow-[inset_-1px_0_0_0_#ffffff1f,inset_0_-1px_0_0_#ffffff3d]';
                                        return (
                                            <th
                                                key={column}
                                                className={`${isReleaseNumber ? 'px-1' : 'px-2'} ${isOldMan ? 'py-2 text-[13px]' : 'py-0.5 text-[11px]'} align-middle text-center font-bold tracking-wide text-gray-700 dark:text-slate-200 bg-gray-100 dark:bg-slate-900 ${headerDividerShadow}`}
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
                                    {showAdminActions && (
                                        <th className="px-1 py-0.5 text-center text-xl font-bold text-gray-700 dark:text-slate-200 uppercase tracking-wider bg-gray-100 dark:bg-slate-900 w-8 shadow-[inset_0_-1px_0_0_#0000005c] dark:shadow-[inset_0_-1px_0_0_#ffffff3d]">
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
                                                    colSpan={tableColumnCount + (showAdminActions ? 1 : 0)}
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
                                                    columns={tableColumns}
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
                                                    showActions={showAdminActions}
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
                                                colSpan={tableColumnCount + (showAdminActions ? 1 : 0)}
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
                                                    colSpan={tableColumnCount + (showAdminActions ? 1 : 0)}
                                                    className={`${ASAP_DIVIDER_BOX_CLASS} border-y`}
                                                >
                                                    <AsapDividerLabel count={row._asapCount} />
                                                </td>
                                            </tr>
                                        ) : (
                                        <JobsTableRow
                                            key={row.id}
                                            row={row}
                                            columns={tableColumns}
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
                                            showActions={showAdminActions}
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

            {drawingModal && (
                <PdfVersionHistoryModal
                    isOpen={true}
                    releaseId={drawingModal.releaseId}
                    title={drawingModal.jobReleaseLabel}
                    initialCommentVersionId={drawingModal.versionId}
                    onClose={() => setDrawingModal(null)}
                    onOpenVersion={(vid, mode) => {
                        setPdfMarkupReleaseId(drawingModal.releaseId);
                        setDrawingModal(null);
                        setPdfMarkupVersionId(vid);
                        setPdfMarkupMode(mode);
                        setPdfMarkupOpen(true);
                    }}
                />
            )}
            <PdfMarkupModal
                isOpen={pdfMarkupOpen}
                releaseId={pdfMarkupReleaseId}
                versionId={pdfMarkupVersionId}
                mode={pdfMarkupMode}
                onClose={() => setPdfMarkupOpen(false)}
            />
        </>
    );
}

export default JobLogContent;
