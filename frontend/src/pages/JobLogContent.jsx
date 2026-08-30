/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Table/cards content for the Job Log (Table view). Renders the filtered releases provided by the persistent ReleasesLayout via Outlet context — device breakpoint picks the mobile card / tablet card / desktop table layout. Owns the release hub so a cards↔table remount on rotate (BUG-14) cannot dump it.
 * exports:
 *   JobLogContent: Child route element for /job-log; consumes useOutletContext() from ReleasesLayout.
 * imports_from: [react, react-router-dom, ../components/ColumnHeaderFilter, ../components/JobsTableRow, ../components/StageIconRow, ../components/AsapPropagationTag, ../components/JobLogCardGrid, ../components/ReleaseHubModal, ../utils/formatters, ../utils/jobLogColumns, ../constants/columnHeaders, ../utils/dialogPersist, ../hooks/usePersistScroll]
 * imported_by: [../App.jsx]
 * invariants:
 *   - All filter state + filtered rows come from ReleasesLayout via context; this component never calls useJobsFilters.
 *   - Column-header dropdown UI renders here but mutates layout state via setColumnFilter/setColumnSort from context (the reactive loop recomputes displayJobs/uniqueValuesByColumn upstream).
 *   - effectiveView (mobilecard/cards/table) is device-driven and orthogonal to the Table/Board/Timeline switch.
 *   - The open ReleaseHubModal lives here, not in JobLogCardGrid / JobsTableRow, so rotating across 1024/1280 cannot close it.
 */
import React, { useRef, useMemo, useState, useEffect, useCallback } from 'react';
import { useOutletContext, useLocation, useNavigate } from 'react-router-dom';
import ColumnHeaderFilter from '../components/ColumnHeaderFilter';
import { JobsTableRow } from '../components/JobsTableRow';
import { PdfVersionHistoryModal } from '../components/PdfVersionHistoryModal';
import { PdfMarkupModal } from '../components/PdfMarkupModal';
import { ReleaseHubModal } from '../components/ReleaseHubModal';
import { AsapDividerLabel, ASAP_DIVIDER_BOX_CLASS } from '../components/AsapPropagationTag';
import JobLogCardGrid from '../components/JobLogCardGrid';
import { formatDateShort, formatCellValue } from '../utils/formatters';
import { FILTERABLE_COLUMNS, DATE_COLUMNS } from '../utils/jobLogColumns';
import { HEADER_OVERRIDES } from '../constants/columnHeaders';
import { persistOpenDialog, readOpenDialog } from '../utils/dialogPersist';
import { usePersistScroll } from '../hooks/usePersistScroll';

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
    const savedTableScroll = useRef(0);
    const savedCardScroll = useRef(0);
    const tableScroll = usePersistScroll(savedTableScroll);
    const cardScroll = usePersistScroll(savedCardScroll);
    const setTableScrollNode = useCallback((node) => {
        tableScrollRef.current = node;
        tableScroll.ref(node);
    }, [tableScroll.ref]);

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
    // Hosted above the cards/table swap so rotate cannot dump it (BUG-14).
    const [hub, setHub] = useState(null); // { job, tab, scrollToMaterials }
    const restoredHub = useRef(false);

    const persistHub = useCallback((next) => {
        if (!next?.job) persistOpenDialog('jl_hub', null);
        else persistOpenDialog('jl_hub', {
            id: next.job.id,
            tab: next.tab || 'details',
            scrollToMaterials: !!next.scrollToMaterials,
        });
    }, []);

    const openHub = useCallback((job, tab = 'details', opts = {}) => {
        const next = { job, tab, scrollToMaterials: !!opts.scrollToMaterials };
        setHub(next);
        persistHub(next);
    }, [persistHub]);

    const closeHub = useCallback(() => {
        setHub(null);
        persistHub(null);
    }, [persistHub]);

    const openHubMarkup = useCallback((payload) => {
        setPdfMarkupReleaseId(payload.releaseId);
        setPdfMarkupVersionId(payload.versionId);
        setPdfMarkupMode(payload.mode || 'view');
        setPdfMarkupOpen(true);
        setHub(null);
        persistHub(null);
    }, [persistHub]);

    useEffect(() => {
        const od = location.state?.openDrawing;
        if (od?.releaseId) {
            setDrawingModal(od);
            // Clear nav state so a refresh or back-navigation doesn't reopen the modal.
            navigate(location.pathname, { replace: true, state: null });
        }
    }, [location.state, location.pathname, navigate]);

    // Reopen the hub after a Safari reload-on-rotate. Wait until rows are in so
    // we have the job object; only run once so a later filter change cannot
    // resurrect a dialog the user closed.
    useEffect(() => {
        if (restoredHub.current || loading) return;
        const saved = readOpenDialog('jl_hub');
        if (!saved?.id) {
            restoredHub.current = true;
            return;
        }
        const job = renderRows.find((r) => r.id === saved.id)
            || secondarySearchResults.find((r) => r.id === saved.id);
        if (!job) return;
        restoredHub.current = true;
        setHub({ job, tab: saved.tab || 'details', scrollToMaterials: !!saved.scrollToMaterials });
    }, [loading, renderRows, secondarySearchResults]);

    // Keep the hosted hub's job object in sync with the live row after refetch.
    useEffect(() => {
        if (!hub?.job) return;
        const fresh = renderRows.find((r) => r.id === hub.job.id)
            || secondarySearchResults.find((r) => r.id === hub.job.id);
        if (fresh && fresh !== hub.job) {
            setHub((h) => (h ? { ...h, job: fresh } : h));
        }
    }, [renderRows, secondarySearchResults, hub?.job]);

    // On iPad/narrow widths the full table doesn't fit in landscape, so drop the two
    // lowest-frequency columns (BY, Released) and re-normalize the remaining widths to
    // 100% (fixed-layout table). Desktop keeps every column; CSV/PDF export are
    // unaffected (they read the full columnHeaders from ReleasesLayout).
    // Zebra band index per row, counting only rows that aren't install-complete.
    // Computed here rather than in the row because a row can't know how many
    // grey rows preceded it. Mirrors JobsTableRow's own `isGrayed` test.
    const bandIndexById = useMemo(() => {
        const map = new Map();
        let band = 0;
        for (const row of renderRows) {
            if (row._asapDivider) continue;
            const stage = (row['Stage'] || '').toString().trim().toLowerCase();
            const done = stage === 'complete'
                || (row['Job Comp'] || '').toString().trim().toUpperCase() === 'X';
            map.set(row.id, done ? -1 : band);
            if (!done) band += 1;
        }
        return map;
    }, [renderRows]);

    const { tableColumns, tableWidthPercents } = useMemo(() => {
        if (isDesktop) return { tableColumns: columnHeaders, tableWidthPercents: columnWidthPercents };
        const NARROW_HIDDEN = new Set(['BY', 'Released']);
        const cols = columnHeaders.filter((c) => !NARROW_HIDDEN.has(c));
        const sum = cols.reduce((acc, c) => acc + (columnWidthPercents[c] ?? 0), 0) || 1;
        const widths = Object.fromEntries(cols.map((c) => [c, ((columnWidthPercents[c] ?? 0) / sum) * 100]));
        return { tableColumns: cols, tableWidthPercents: widths };
    }, [isDesktop, columnHeaders, columnWidthPercents]);

    // Row-actions column (⋯ menu) is desktop-only (14"+ screens). Admins get
    // Edit + Delete; drafters get Edit only (DP: job→released fields via modal).
    // Gates the header cell, per-row actions, and colSpan math so the table stays aligned.
    const showRowActions = (isAdmin || isDrafter) && isDesktop;

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
                    onOpenHub={openHub}
                    onOpenMarkup={openHubMarkup}
                    scrollRef={cardScroll.ref}
                    onScroll={cardScroll.onScroll}
                />
            )}

            {!loading && !fetchError && effectiveView === 'table' && (
                // Lattice CSS: tokens.css .job-log-table-frame / .job-log-table
                // (separate borders — collapse caused the left-edge hairline gap).
                <div className="job-log-table-frame flex-1 min-h-0 flex flex-col">
                    <div
                        ref={setTableScrollNode}
                        onScroll={tableScroll.onScroll}
                        className="job-log-table-scroll overflow-auto flex-1"
                    >
                        <table className="job-log-table">
                            <thead className="sticky top-0 z-10">
                                <tr>
                                    {tableColumns.map((column) => {
                                        const isReleaseNumber = column === 'Release #';
                                        const displayHeader = HEADER_OVERRIDES[column] ?? column;
                                        const colWidthPct = tableWidthPercents[column];
                                        const isFilterable = FILTERABLE_COLUMNS.has(column);
                                        const colInfo = isFilterable ? uniqueValuesByColumn[column] : null;
                                        const colSelected = columnFilters[column] ?? [];
                                        return (
                                            <th
                                                key={column}
                                                className={`${isReleaseNumber ? 'px-0.5' : 'px-1'} ${isOldMan ? 'py-2' : 'py-1.5'} text-jl-head align-middle text-center font-bold text-ink bg-head-bg leading-tight`}
                                                style={colWidthPct != null ? { width: `${colWidthPct}%` } : undefined}
                                            >
                                                {isFilterable ? (
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
                                                    <span className="block w-full text-center leading-tight">{displayHeader}</span>
                                                )}
                                            </th>
                                        );
                                    })}
                                    {showRowActions && (
                                        <th className="px-1 py-0.5 text-center text-xl font-bold text-ink uppercase tracking-wider bg-head-bg w-8">
                                            ⚙
                                        </th>
                                    )}
                                </tr>
                            </thead>
                            <tbody>
                                {/* Zebra counts only rows that aren't install-complete
                                    (handoff §3 banding rule): a grey row must not consume
                                    an alternation step, or the bands either side of it
                                    come out the same shade. */}
                                {renderRows.length === 0 ? (
                                    hasJobsData && search.trim() !== '' && secondarySearchResults.length > 0 ? (
                                        <>
                                            <tr>
                                                <td
                                                    colSpan={tableColumnCount + (showRowActions ? 1 : 0)}
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
                                                    showActions={showRowActions}
                                                    isDrafter={isDrafter}
                                                    onDelete={handleDeleteJob}
                                                    tableScrollRef={tableScrollRef}
                                                    duplicateFabOrders={duplicateFabOrders}
                                                    onOpenReleaseHub={openHub}
                                                    onOpenReleaseMarkup={openHubMarkup}
                                                />
                                            ))}
                                        </>
                                    ) : (
                                        <tr>
                                            <td
                                                colSpan={tableColumnCount + (showRowActions ? 1 : 0)}
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
                                                    colSpan={tableColumnCount + (showRowActions ? 1 : 0)}
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
                                            bandIndex={bandIndexById.get(row.id) ?? index}
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
                                            showActions={showRowActions}
                                            isDrafter={isDrafter}
                                            onDelete={handleDeleteJob}
                                            tableScrollRef={tableScrollRef}
                                            duplicateFabOrders={duplicateFabOrders}
                                            onOpenReleaseHub={openHub}
                                            onOpenReleaseMarkup={openHubMarkup}
                                        />
                                        )
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            <ReleaseHubModal
                isOpen={hub?.job != null}
                onClose={closeHub}
                job={hub?.job}
                releaseId={hub?.job?.id}
                viewerUrl={hub?.job?.viewer_url}
                initialTab={hub?.tab || 'details'}
                scrollToMaterials={!!hub?.scrollToMaterials}
                onOrdersChanged={() => refetch(true)}
                onNotesChanged={(notes) => {
                    setHub((h) => (h ? { ...h, job: { ...h.job, 'Notes': notes, notes } } : h));
                    refetch(true);
                }}
                onOpenVersion={(vid, mode) => {
                    openHubMarkup({
                        releaseId: hub?.job?.id,
                        versionId: vid,
                        mode,
                    });
                }}
            />

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
