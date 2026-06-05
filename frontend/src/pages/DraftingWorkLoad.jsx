/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Primary submittal tracking page that lets drafters and admins view, filter, reorder, and update Procore submittals across Open and Draft tabs.
 * exports:
 *   DraftingWorkLoad: Page component with tabbed submittal table, drag-and-drop ordering, inline editing, and PDF export
 * imports_from: [react, react-router-dom, ../hooks/useDataFetching, ../hooks/useFilters, ../hooks/useDWLDragAndDrop, ../components/TableRow, ../services/draftingWorkLoadApi, ../context/LocationContext]
 * imported_by: [App.jsx]
 * invariants:
 *   - Admin-only actions: reorder, resort, add project, bump, step order, change Procore status
 *   - Drafter-or-admin actions: update status, update due date
 *   - When a highlight query param is present, all tabs are fetched so the target row can be found
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import React, { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useJumpToHighlight } from '../hooks/useJumpToHighlight';
import { useDataFetching } from '../hooks/useDataFetching';
import { useMutations } from '../hooks/useMutations';
import { useFilters } from '../hooks/useFilters';
import { useDWLDragAndDrop } from '../hooks/useDWLDragAndDrop';
import { TableRow } from '../components/TableRow';
import ColumnHeaderFilter from '../components/ColumnHeaderFilter';
import { AlertMessage } from '../components/AlertMessage';
import { AddProjectModal } from '../components/AddProjectModal';
import { generateDraftingWorkLoadPDF } from '../utils/pdfUtils';
import { formatDate, formatCellValue } from '../utils/formatters';
import { checkAuth } from '../utils/auth';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';
import { fetchMentionableUsers } from '../services/notificationApi';
import { useLocationContext } from '../context/LocationContext';
import ViewToggle, { useViewMode } from '../components/ViewToggle';
import SubmittalRowList from '../components/SubmittalRowList';
import { useBreakpoint, useIsTabletOrSmaller } from '../hooks/useBreakpoint';

// Responsive column width styles for larger screens (2xl breakpoint: 1536px+)
// Laptop sizes are kept as default (max-width only), only larger screens get adjusted max-widths
const columnWidthStyles = `
    @media (min-width: 1536px) {
        /* Reduce column max-widths on very large screens to prevent bloating */
        .dwl-col-name { max-width: 260px !important; }
        .dwl-col-title { max-width: 250px !important; }
        .dwl-col-bic { max-width: 160px !important; }
        .dwl-col-sub-manager { max-width: 120px !important; }
        .dwl-col-notes { max-width: 300px !important; }
        .dwl-col-submittal-id { max-width: 128px !important; }
    }
`;

// Friendly labels + display order for the active-filter chips (keys match useFilters' columnFilters).
const FILTER_LABELS = {
    'PROJ. #': 'Project #',
    'NAME': 'Project Name',
    'TITLE': 'Title',
    'BIC': 'Ball in Court',
    'SUB MANAGER': 'Sub Manager',
    'PROCORE STATUS': 'Procore Status',
};
const FILTER_CHIP_ORDER = ['PROJ. #', 'NAME', 'TITLE', 'BIC', 'SUB MANAGER', 'PROCORE STATUS'];

function DraftingWorkLoad() {
    const [searchParams] = useSearchParams();
    const { locationFilter } = useLocationContext();
    const [resorting, setResorting] = useState(false);
    const [resortError, setResortError] = useState(null);
    const [addProjectOpen, setAddProjectOpen] = useState(false);
    const [viewMode, setViewMode] = useViewMode('dwl_view', 'auto');
    const isTabletOrSmaller = useIsTabletOrSmaller();
    const { is3xl } = useBreakpoint();
    const effectiveView = viewMode === 'auto' ? (isTabletOrSmaller ? 'cards' : 'table') : viewMode;
    // Tab state: 'open' or 'draft' — passed to API so backend returns tab-specific submittals
    const [selectedTab, setSelectedTab] = useState('open');
    // When a jump-to param is present, load all tabs so we can find the row regardless of its status
    const hasJumpToParam = searchParams.has('highlight');
    const tabForFetch = hasJumpToParam ? 'all' : selectedTab;
    const { submittals, columns, loading, error: fetchError, lastUpdated, refetch } = useDataFetching(locationFilter, tabForFetch);
    const {
        updateOrderNumber,
        updateNotes,
        updateStatus,
        updateProcoreStatus,
        bumpSubmittal,
        updateDueDate,
        stepSubmittal,
    } = useMutations(refetch);

    // Submittal statuses for company (Procore status dropdown on draft tab)
    const [submittalStatuses, setSubmittalStatuses] = useState([]);
    useEffect(() => {
        draftingWorkLoadApi.fetchSubmittalStatuses()
            .then(setSubmittalStatuses)
            .catch((err) => console.error('Failed to fetch submittal statuses:', err));
    }, []);

    // Global Total Fab HRS (same figure shown on the Job Log header), fetched
    // once from a lightweight aggregation endpoint. Independent of DWL filters.
    const [totalFabHrs, setTotalFabHrs] = useState(null);
    useEffect(() => {
        draftingWorkLoadApi.fetchFabHoursTotal()
            .then(setTotalFabHrs)
            .catch((err) => console.error('Failed to fetch total fab hours:', err));
    }, []);

    // Mentionable users for @mention autocomplete in the notes field
    const [mentionableUsers, setMentionableUsers] = useState([]);
    useEffect(() => {
        fetchMentionableUsers()
            .then(setMentionableUsers)
            .catch(() => {});
    }, []);

    // User role status
    const [isAdmin, setIsAdmin] = useState(false);
    const [isDrafter, setIsDrafter] = useState(false);
    const [userLoading, setUserLoading] = useState(true);
    const canEditDrafterFields = isAdmin || isDrafter;

    // Fetch user info to check role status
    useEffect(() => {
        const fetchUserInfo = async () => {
            try {
                const user = await checkAuth();
                setIsAdmin(user?.is_admin || false);
                setIsDrafter(user?.is_drafter || false);
            } catch (err) {
                console.error('Error fetching user info:', err);
                setIsAdmin(false);
                setIsDrafter(false);
            } finally {
                setUserLoading(false);
            }
        };
        fetchUserInfo();
    }, []);

    // Ref for scroll container to preserve scroll position on bump
    const scrollContainerRef = useRef(null);

    // Backend returns tab-specific data (open = Open status, draft = not Open/Closed), so use submittals as rows
    const rows = submittals;

    // Use the filters hook
    const {
        search,
        columnFilters,
        columnSort,
        setSearch,
        setColumnFilter,
        handleColumnSort,
        setColumnSortDirect,
        resetFilters,
        uniqueValuesByColumn,
        singleSelectedBallInCourt,
        displayRows,
    } = useFilters(rows);

    // Use the drag-and-drop hook
    const {
        draggedRow,
        dragOverSubmittalId,
        dragOverHalf,
        handleDragStart,
        handleDragOver,
        handleDragLeave,
        handleDragEnd,
        handleDrop,
    } = useDWLDragAndDrop(rows, refetch, isAdmin);

    const jumpToTarget = useJumpToHighlight({
        loading,
        searchParams,
        mode: 'submittal',
    });

    const handleResort = useCallback(async () => {
        if (!singleSelectedBallInCourt) return;
        setResorting(true);
        setResortError(null);
        try {
            await draftingWorkLoadApi.resortDrafter(singleSelectedBallInCourt);
            await refetch();
        } catch (err) {
            setResortError(err.message);
        } finally {
            setResorting(false);
        }
    }, [singleSelectedBallInCourt, refetch]);

    const handleGeneratePDF = useCallback(() => {
        generateDraftingWorkLoadPDF(displayRows, columns, lastUpdated);
    }, [displayRows, columns, lastUpdated]);

    // Priority filter dropdowns in the toolbar (Project / BIC / Sub Manager). These share the
    // SAME columnFilters state as the spreadsheet-style column-header filters, so the two surfaces
    // stay mirrored and stack additively with each other and with other columns' filters.
    // Single-select by default; Ctrl/Cmd+click adds more.
    const renderToolbarFilter = (column, label) => {
        const colInfo = uniqueValuesByColumn[column];
        const colSelected = columnFilters[column] ?? [];
        return (
            <ColumnHeaderFilter
                column={column}
                values={colInfo?.values ?? []}
                hasBlanks={colInfo?.hasBlanks ?? false}
                selected={new Set(colSelected)}
                onChange={(next) => setColumnFilter(column, [...next])}
                sort={columnSort}
                onSort={(dir) => setColumnSortDirect(column, dir)}
                isActive={colSelected.length > 0}
                autoWidth
                singleSelect
                immediate
            >
                <span
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded border text-xs font-semibold whitespace-nowrap ${colSelected.length > 0
                        ? 'bg-blue-700 text-white border-blue-700'
                        : 'bg-white dark:bg-slate-600 border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200'}`}
                >
                    {label}{colSelected.length > 0 ? ` (${colSelected.length})` : ''}
                    <span className="text-[0.65rem] leading-none">▾</span>
                </span>
            </ColumnHeaderFilter>
        );
    };

    const handleBump = useCallback(async (submittalId) => {
        const container = scrollContainerRef.current;
        const scrollTop = container ? container.scrollTop : 0;
        await bumpSubmittal(submittalId);
        if (container) {
            requestAnimationFrame(() => {
                container.scrollTop = scrollTop;
            });
        }
    }, [bumpSubmittal]);

    const formattedLastUpdated = useMemo(
        () => lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Unknown',
        [lastUpdated]
    );

    // Active per-column filters, as removable chips — one chip per selected value
    // so multiple selections in the same column (e.g. two BICs) each show and can
    // be removed individually.
    const activeFilterChips = useMemo(
        () => FILTER_CHIP_ORDER
            .filter((col) => (columnFilters[col]?.length ?? 0) > 0)
            .flatMap((col) => columnFilters[col].map((value) => ({
                column: col,
                value,
                label: FILTER_LABELS[col] ?? col,
            }))),
        [columnFilters]
    );

    const hasData = displayRows.length > 0;
    const visibleColumns = columns.filter(column => column !== 'Submittals Id');
    // Column display names are case-sensitive: ORDER #, PROJ. #, NAME, TITLE, etc.
    const tableColumnCount = visibleColumns.length;

    return (
        <>
            <style>{columnWidthStyles}</style>
            <div
                className="w-full h-[calc(100vh-3.5rem)] 3xl:h-[calc(100vh-4rem)] flex flex-col bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900"
                style={{
                    width: '100%',
                    minWidth: '100%',
                    paddingLeft: 'env(safe-area-inset-left)',
                    paddingRight: 'env(safe-area-inset-right)',
                    paddingBottom: 'env(safe-area-inset-bottom)',
                }}
            >
                <div className="flex-1 min-h-0 max-w-full mx-auto w-full py-2 px-2 flex flex-col" style={{ width: '100%' }}>
                    <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl overflow-hidden flex flex-col flex-1 min-h-0">
                        {/* Actions + Filters - fixed, do not scroll */}
                        <div className="flex-shrink-0 p-2">
                            <div className="bg-gray-100 dark:bg-slate-700 rounded-lg p-1.5 border border-gray-200 dark:border-slate-600 flex-shrink-0 space-y-1.5">
                                {/* Row 2: view mode + primary CTA + Actions + Open/Draft + priority filters */}
                                <div className="flex items-center gap-1.5 flex-wrap">
                                    <ViewToggle value={viewMode} onChange={setViewMode} />

                                    <div className="flex-1" />

                                    {/* Centered primary filters — share state with the spreadsheet column filters.
                                        Open/Draft is the rightmost element of this centered group. */}
                                    <div className="flex items-center gap-1.5 flex-wrap justify-center">
                                        <span className="text-xs font-semibold text-gray-600 dark:text-slate-300 whitespace-nowrap">Filter:</span>
                                        {renderToolbarFilter('NAME', 'Project')}
                                        {renderToolbarFilter('BIC', 'BIC')}
                                        {renderToolbarFilter('SUB MANAGER', 'Sub Mgr')}
                                        {/* Open / Draft segmented — rightmost element of the centered filters */}
                                        <div className="inline-flex rounded-md border border-gray-400 dark:border-slate-500 overflow-hidden">
                                            <button
                                                onClick={() => setSelectedTab('open')}
                                                className={`px-3 py-1 text-xs font-semibold transition-all whitespace-nowrap ${selectedTab === 'open'
                                                    ? 'bg-blue-700 text-white'
                                                    : 'bg-white dark:bg-slate-600 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500'
                                                    }`}
                                            >
                                                Open
                                            </button>
                                            <button
                                                onClick={() => setSelectedTab('draft')}
                                                className={`px-3 py-1 text-xs font-semibold transition-all whitespace-nowrap border-l border-gray-400 dark:border-slate-500 ${selectedTab === 'draft'
                                                    ? 'bg-blue-700 text-white'
                                                    : 'bg-white dark:bg-slate-600 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500'
                                                    }`}
                                            >
                                                Draft
                                            </button>
                                        </div>
                                    </div>

                                    <div className="flex-1" />

                                    {resorting && (
                                        <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-700 dark:text-blue-300" role="status" aria-live="polite">
                                            <span className="inline-block h-3.5 w-3.5 rounded-full border-2 border-blue-300 border-t-blue-700 dark:border-slate-600 dark:border-t-blue-300 animate-spin" />
                                            Resorting…
                                        </span>
                                    )}

                                    {/* Actions (right): New Project · Resort · Print — admin-only */}
                                    {isAdmin && (
                                        <button
                                            onClick={() => setAddProjectOpen(true)}
                                            className="px-3 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap inline-flex items-center gap-1 bg-blue-700 text-white border border-blue-700 hover:bg-blue-800"
                                            title="Add a new Procore project to the system"
                                        >
                                            <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><path d="M7 2v10M2 7h10" /></svg>New Project
                                        </button>
                                    )}
                                    {isAdmin && (
                                        <>
                                            <button
                                                onClick={handleResort}
                                                disabled={!singleSelectedBallInCourt || resorting}
                                                title={!singleSelectedBallInCourt
                                                    ? 'Filter the BIC column to a single drafter to enable resort'
                                                    : `Compress ${singleSelectedBallInCourt}'s ordered submittals to sequential numbers`}
                                                className="px-3 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-500 disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                {resorting ? 'Resorting\u2026' : '\u2195 Resort'}
                                            </button>
                                            <button
                                                onClick={handleGeneratePDF}
                                                disabled={!hasData || loading}
                                                title="Generate PDF"
                                                className="px-3 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-500 disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                🖨️ Print/PDF
                                            </button>
                                        </>
                                    )}
                                </div>

                                {/* Row 3: Search + meta — always visible */}
                                <div className="flex items-center justify-between gap-1.5 flex-wrap">
                                    <div className="flex items-center gap-1.5 flex-wrap">
                                        <div className="flex items-center gap-1.5">
                                            <label className="text-xs font-semibold text-gray-700 dark:text-slate-200 whitespace-nowrap">Search:</label>
                                            <input
                                                type="text"
                                                value={search}
                                                onChange={(e) => setSearch(e.target.value)}
                                                placeholder="Project, title, BIC, manager…"
                                                className="w-48 sm:w-64 px-2 py-2 md:py-0.5 text-sm md:text-xs border border-gray-300 dark:border-slate-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-slate-600 text-gray-900 dark:text-slate-100"
                                            />
                                        </div>
                                        <button
                                            onClick={resetFilters}
                                            className="text-sm text-blue-600 dark:text-blue-400 underline hover:no-underline whitespace-nowrap"
                                        >
                                            Reset Filters
                                        </button>
                                    </div>
                                    <div className="flex items-center gap-3 text-sm font-semibold text-gray-700 dark:text-slate-200">
                                        <span>
                                            Total: <span className="text-gray-900 dark:text-slate-100 font-bold">{displayRows.length}</span> records
                                        </span>
                                        <span className="text-gray-300 dark:text-slate-500">|</span>
                                        <span>
                                            Fab HRS: <span className="text-gray-900 dark:text-slate-100 font-bold">{Number.isFinite(totalFabHrs) ? totalFabHrs.toFixed(2) : '—'}</span>
                                        </span>
                                        <span className="text-gray-300 dark:text-slate-500">|</span>
                                        <span className="text-gray-500 dark:text-slate-400 font-normal">
                                            Last updated: <span className="font-semibold text-gray-700 dark:text-slate-200">{formattedLastUpdated}</span>
                                        </span>
                                    </div>
                                </div>

                                {/* Active filter chips */}
                                {activeFilterChips.length > 0 && (
                                    <div className="flex items-center gap-1.5 flex-wrap border-t border-gray-200 dark:border-slate-600 pt-2">
                                        <span className="text-xs font-semibold text-gray-500 dark:text-slate-400 whitespace-nowrap">Active filters:</span>
                                        {activeFilterChips.map((chip) => (
                                            <span
                                                key={`${chip.column}:${chip.value}`}
                                                className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 text-blue-700 dark:text-blue-300 text-xs font-medium"
                                            >
                                                <span className="whitespace-nowrap">{chip.label}: {chip.value}</span>
                                                <button
                                                    type="button"
                                                    onClick={() => setColumnFilter(chip.column, (columnFilters[chip.column] ?? []).filter((v) => v !== chip.value))}
                                                    className="flex items-center justify-center w-4 h-4 rounded-full leading-none text-blue-500 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-800 hover:text-blue-800 dark:hover:text-blue-100 transition-colors"
                                                    aria-label={`Remove ${chip.label} filter ${chip.value}`}
                                                    title={`Remove ${chip.label}: ${chip.value}`}
                                                >
                                                    ×
                                                </button>
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>

                        {loading && (
                            <div className="flex-shrink-0 text-center py-12">
                                <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                                <p className="text-gray-600 dark:text-slate-400 font-medium">Loading Drafting Work Load data...</p>
                            </div>
                        )}

                        {fetchError && !loading && (
                            <div className="flex-shrink-0 p-2">
                                <AlertMessage
                                    type="error"
                                    title="Unable to load Drafting Work Load data"
                                    message={fetchError}
                                />
                            </div>
                        )}

                        {resortError && (
                            <div className="flex-shrink-0 p-2">
                                <AlertMessage type="error" title="Resort failed" message={resortError} />
                            </div>
                        )}

                        {!loading && !fetchError && effectiveView === 'cards' && (
                            <div className="flex-1 min-h-0 flex flex-col border border-gray-200 dark:border-slate-600 rounded-xl overflow-hidden bg-white dark:bg-slate-800 min-w-0">
                                <SubmittalRowList
                                    rows={displayRows}
                                    jumpToTarget={jumpToTarget}
                                />
                            </div>
                        )}

                        {!loading && !fetchError && effectiveView === 'table' && (
                            <div className="flex-1 min-h-0 flex flex-col border border-gray-200 dark:border-slate-600 rounded-xl overflow-hidden bg-white dark:bg-slate-800 min-w-0">
                                <div
                                    ref={scrollContainerRef}
                                    className="dwl-table-scroll flex-1 min-h-0 overflow-x-hidden"
                                    style={{ overflowY: 'auto' }}
                                >
                                    <table className="w-full" style={{ borderCollapse: 'collapse', width: '100%', tableLayout: 'fixed' }}>
                                        <thead className="sticky top-0 z-10 bg-gray-100 dark:bg-slate-700 shadow-sm">
                                            <tr>
                                                {visibleColumns.map((column) => {
                                                    const isOrderNumber = column === 'ORDER #';
                                                    const isNotes = column === 'NOTES';
                                                    const isProjectName = column === 'NAME';
                                                    const isTitle = column === 'TITLE';
                                                    const isProcoreStatus = column === 'PROCORE STATUS';
                                                    const isStatus = column === 'COMP. STATUS';
                                                    const isBallInCourt = column === 'BIC';
                                                    const isType = column === 'TYPE';
                                                    const isSubmittalId = column === 'Submittals Id';
                                                    const isProjectNumber = column === 'PROJ. #';
                                                    const isSubmittalManager = column === 'SUB MANAGER';
                                                    const isDueDate = column === 'DUE DATE';

                                                    // Percentage widths (must total 100%). PROCORE STATUS gets more space.
                                                    let headerStyle = {};
                                                    let columnClass = '';
                                                    if (isOrderNumber) {
                                                        headerStyle = { width: '6%' };
                                                        columnClass = 'dwl-col-order-number';
                                                    } else if (isProjectNumber) {
                                                        headerStyle = { width: '4%' };
                                                        columnClass = 'dwl-col-project-number';
                                                    } else if (isTitle) {
                                                        headerStyle = { width: '12%' };
                                                        columnClass = 'dwl-col-title';
                                                    } else if (isNotes) {
                                                        headerStyle = { width: '14%' };
                                                        columnClass = 'dwl-col-notes';
                                                    } else if (isBallInCourt) {
                                                        headerStyle = { width: '8%' };
                                                        columnClass = 'dwl-col-bic';
                                                    } else if (isType) {
                                                        headerStyle = { width: '4%' };
                                                        columnClass = 'dwl-col-type';
                                                    } else if (isProcoreStatus) {
                                                        headerStyle = { width: '9%' };
                                                        columnClass = 'dwl-col-procore-status';
                                                    } else if (isStatus) {
                                                        headerStyle = { width: '5%' };
                                                        columnClass = 'dwl-col-comp-status';
                                                    } else if (isSubmittalManager) {
                                                        headerStyle = { width: '7%' };
                                                        columnClass = 'dwl-col-sub-manager';
                                                    } else if (isDueDate) {
                                                        headerStyle = { width: '6%' };
                                                        columnClass = 'dwl-col-due-date';
                                                    } else if (isProjectName) {
                                                        headerStyle = { width: '12%' };
                                                        columnClass = 'dwl-col-name';
                                                    }

                                                    // Reduce padding for specific columns
                                                    const isProjectNumberHeader = column === 'PROJ. #';
                                                    const headerPaddingClass = isOrderNumber ? 'px-0.5 py-0.5' : isProjectNumberHeader ? 'px-0.5 py-0.5' : 'px-1 py-0.5';

                                                    // Determine if this column is sortable
                                                    // ORDER #, NOTES, PROCORE STATUS, COMP. STATUS are not sortable (interactive); DUE DATE is sortable (asc/desc)
                                                    const isNotSortable = isOrderNumber || isNotes || isProcoreStatus || isStatus;

                                                    // Get sort state for this column
                                                    const isSorted = columnSort.column === column;
                                                    const sortDirection = isSorted ? columnSort.direction : null;

                                                    // Excel-style header dropdown filter for these columns
                                                    const isFilterable = isProjectNumber || isProjectName || isTitle || isBallInCourt || isSubmittalManager || isProcoreStatus;
                                                    if (isFilterable) {
                                                        const colInfo = uniqueValuesByColumn[column];
                                                        const colSelected = columnFilters[column] ?? [];
                                                        return (
                                                            <th
                                                                key={column}
                                                                className={`${headerPaddingClass} text-center text-xs font-bold text-gray-900 dark:text-slate-100 uppercase tracking-wider bg-gray-100 dark:bg-slate-700 border-r border-gray-300 dark:border-slate-600 ${columnClass}`}
                                                                style={headerStyle}
                                                            >
                                                                <ColumnHeaderFilter
                                                                    column={column}
                                                                    values={colInfo?.values ?? []}
                                                                    hasBlanks={colInfo?.hasBlanks ?? false}
                                                                    selected={new Set(colSelected)}
                                                                    onChange={(next) => setColumnFilter(column, [...next])}
                                                                    sort={columnSort}
                                                                    onSort={(dir) => setColumnSortDirect(column, dir)}
                                                                    isActive={colSelected.length > 0}
                                                                    autoWidth
                                                                    singleSelect={isBallInCourt}
                                                                >
                                                                    {column}
                                                                </ColumnHeaderFilter>
                                                            </th>
                                                        );
                                                    }

                                                    // Render sortable column header
                                                    if (!isNotSortable) {
                                                        return (
                                                            <th
                                                                key={column}
                                                                className={`${headerPaddingClass} text-center text-xs font-bold text-gray-900 dark:text-slate-100 uppercase tracking-wider bg-gray-100 dark:bg-slate-700 border-r border-gray-300 dark:border-slate-600 ${columnClass}`}
                                                                style={headerStyle}
                                                            >
                                                                <button
                                                                    onClick={() => handleColumnSort(column)}
                                                                    className="flex items-center justify-center gap-1 hover:bg-gray-200 dark:hover:bg-slate-600 rounded px-1 py-0.5 transition-colors w-full"
                                                                    title={
                                                                        sortDirection === null ? 'Click to sort ascending' :
                                                                            sortDirection === 'asc' ? 'Click to sort descending' :
                                                                                'Click to remove sort'
                                                                    }
                                                                >
                                                                    <span>{column}</span>
                                                                    {sortDirection === 'asc' && <span className="text-xs">↑</span>}
                                                                    {sortDirection === 'desc' && <span className="text-xs">↓</span>}
                                                                    {sortDirection === null && <span className="text-xs text-gray-400 dark:text-slate-400">↕</span>}
                                                                </button>
                                                            </th>
                                                        );
                                                    }

                                                    // Non-sortable column (Order Number, Notes, Procore Status, Comp. Status)
                                                    return (
                                                        <th
                                                            key={column}
                                                            className={`${headerPaddingClass} text-center text-xs font-bold text-gray-900 dark:text-slate-100 uppercase tracking-wider bg-gray-100 dark:bg-slate-700 border-r border-gray-300 dark:border-slate-600 ${columnClass}`}
                                                            style={headerStyle}
                                                        >
                                                            {column}
                                                        </th>
                                                    );
                                                })}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {!hasData ? (
                                                <tr>
                                                    <td
                                                        colSpan={tableColumnCount}
                                                        className="px-6 py-12 text-center text-gray-500 dark:text-slate-400 font-medium bg-white dark:bg-slate-800 rounded-md"
                                                    >
                                                        No records match the selected filters.
                                                    </td>
                                                </tr>
                                            ) : (
                                                displayRows.map((row, index) => {
                                                    const currentSubmittalId = row['Submittals Id'] ?? row.submittal_id;
                                                    const isDragOver = dragOverSubmittalId === currentSubmittalId;
                                                    return (
                                                        <TableRow
                                                            key={row.id}
                                                            row={row}
                                                            columns={columns}
                                                            isJumpToHighlight={jumpToTarget && String(row['Submittals Id'] ?? row.submittal_id ?? '') === jumpToTarget}
                                                            formatCellValue={formatCellValue}
                                                            formatDate={formatDate}
                                                            onOrderNumberChange={isAdmin ? updateOrderNumber : undefined}
                                                            onNotesChange={updateNotes}
                                                            onStatusChange={updateStatus}
                                                            onProcoreStatusChange={isAdmin ? updateProcoreStatus : undefined}
                                                            procoreStatusOptions={submittalStatuses}
                                                            selectedTab={selectedTab}
                                                            onBump={isAdmin ? handleBump : undefined}
                                                            onDueDateChange={canEditDrafterFields ? updateDueDate : undefined}
                                                            onStepOrder={isAdmin ? stepSubmittal : undefined}
                                                            allRows={rows}
                                                            rowIndex={index}
                                                            isAdmin={isAdmin}
                                                            isDrafter={isDrafter}
                                                            onDragStart={isAdmin ? handleDragStart : undefined}
                                                            onDragOver={isAdmin ? handleDragOver : undefined}
                                                            onDragLeave={isAdmin ? handleDragLeave : undefined}
                                                            onDragEnd={isAdmin ? handleDragEnd : undefined}
                                                            onDrop={isAdmin ? handleDrop : undefined}
                                                            isDragOver={isDragOver}
                                                            dragOverHalf={dragOverHalf}
                                                            mentionableUsers={mentionableUsers}
                                                        />
                                                    );
                                                })
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        <AddProjectModal isOpen={addProjectOpen} onClose={() => setAddProjectOpen(false)} />
        </>
    );
}

export default DraftingWorkLoad;

