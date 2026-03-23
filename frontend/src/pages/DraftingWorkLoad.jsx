import React, { useCallback, useMemo, useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useJumpToHighlight } from '../hooks/useJumpToHighlight';
import { useDataFetching } from '../hooks/useDataFetching';
import { useMutations } from '../hooks/useMutations';
import { useFilters } from '../hooks/useFilters';
import { useDWLDragAndDrop } from '../hooks/useDWLDragAndDrop';
import { TableRow } from '../components/TableRow';
import { FilterButtonGroup } from '../components/FilterButtonGroup';
import { AlertMessage } from '../components/AlertMessage';
import { AddProjectModal } from '../components/AddProjectModal';
import { generateDraftingWorkLoadPDF } from '../utils/pdfUtils';
import { formatDate, formatCellValue } from '../utils/formatters';
import { checkAuth } from '../utils/auth';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';
import { useLocationContext } from '../context/LocationContext';

// Responsive column width styles for larger screens (2xl breakpoint: 1536px+)
// Laptop sizes are kept as default (max-width only), only larger screens get adjusted max-widths
const columnWidthStyles = `
    /* Hide scrollbar on table scroll area; scrolling still works via wheel/trackpad */
    .dwl-table-scroll-hide-scrollbar {
        scrollbar-width: none; /* Firefox */
        -ms-overflow-style: none; /* IE / Edge */
    }
    .dwl-table-scroll-hide-scrollbar::-webkit-scrollbar {
        display: none; /* Chrome, Safari, Edge */
    }
    @media (min-width: 1536px) {
        /* Reduce column max-widths on very large screens to prevent bloating */
        .dwl-col-name { max-width: 260px !important; }
        .dwl-col-title { max-width: 250px !important; }
        .dwl-col-bic { max-width: 160px !important; }
        .dwl-col-sub-manager { max-width: 120px !important; }
        .dwl-col-notes { max-width: 300px !important; }
        .dwl-col-submittal-id { max-width: 128px !important; }
        .dwl-col-last-bic-update { max-width: 100px !important; }
        .dwl-col-lifespan { max-width: 75px !important; }
    }
`;

function DraftingWorkLoad() {
    const [searchParams] = useSearchParams();
    const { locationFilter } = useLocationContext();
    const [resorting, setResorting] = useState(false);
    const [resortError, setResortError] = useState(null);
    const [addProjectOpen, setAddProjectOpen] = useState(false);
    const [isFilterMinimized, setIsFilterMinimized] = useState(false);
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
        selectedBallInCourt,
        selectedSubmittalManager,
        selectedProjectName,
        selectedProcoreStatus,
        projectNameSortMode,
        columnSort,
        setSelectedBallInCourt,
        setSelectedSubmittalManager,
        setSelectedProjectName,
        setSelectedProcoreStatus,
        ballInCourtOptions,
        submittalManagerOptions,
        projectNameOptions,
        procoreStatusOptions,
        displayRows,
        resetFilters,
        handleProjectNameSortToggle,
        handleColumnSort,
        ALL_OPTION_VALUE,
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
        if (selectedBallInCourt === ALL_OPTION_VALUE) return;
        setResorting(true);
        setResortError(null);
        try {
            await draftingWorkLoadApi.resortDrafter(selectedBallInCourt);
            await refetch();
        } catch (err) {
            setResortError(err.message);
        } finally {
            setResorting(false);
        }
    }, [selectedBallInCourt, ALL_OPTION_VALUE, refetch]);

    const handleGeneratePDF = useCallback(() => {
        generateDraftingWorkLoadPDF(displayRows, columns, lastUpdated);
    }, [displayRows, columns, lastUpdated]);

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

    const hasData = displayRows.length > 0;
    const visibleColumns = columns.filter(column => column !== 'Submittals Id');
    // Column display names are case-sensitive: ORDER #, PROJ. #, NAME, TITLE, etc.
    const tableColumnCount = visibleColumns.length;

    return (
        <>
            <style>{columnWidthStyles}</style>
            <div className="w-full h-[calc(100vh-3.5rem)] flex flex-col bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900" style={{ width: '100%', minWidth: '100%' }}>
                <div className="flex-1 min-h-0 max-w-full mx-auto w-full py-2 px-2 flex flex-col" style={{ width: '100%' }}>
                    <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl overflow-hidden flex flex-col flex-1 min-h-0">
                        {/* Title bar - fixed, does not scroll */}
                        <div className={`flex-shrink-0 px-4 py-3 ${selectedTab === 'draft' ? 'bg-gradient-to-r from-green-500 to-green-600' : 'bg-gradient-to-r from-accent-500 to-accent-600'}`}>
                            <div className="flex items-center justify-between">
                                <div>
                                    <h1 className="text-3xl font-bold text-white">Drafting Work Load</h1>
                                </div>
                                <div className="flex items-center gap-3">
                                    {isAdmin && (
                                    <button
                                        onClick={() => setAddProjectOpen(true)}
                                        className="inline-flex items-center px-4 py-2 rounded-lg font-medium shadow-sm transition-all bg-white dark:bg-slate-700 text-accent-600 dark:text-accent-300 hover:bg-accent-50 dark:hover:bg-slate-600 cursor-pointer"
                                        title="Add a new Procore project to the system"
                                    >
                                        + Add Project
                                    </button>
                                    )}
                                    {isAdmin && (
                                    <button
                                        onClick={handleResort}
                                        disabled={selectedBallInCourt === ALL_OPTION_VALUE || resorting}
                                        className={`inline-flex items-center px-4 py-2 rounded-lg font-medium shadow-sm transition-all ${
                                            selectedBallInCourt === ALL_OPTION_VALUE || resorting
                                                ? 'bg-gray-300 dark:bg-slate-600 text-gray-500 dark:text-slate-400 cursor-not-allowed'
                                                : 'bg-white dark:bg-slate-700 text-accent-600 dark:text-accent-300 hover:bg-accent-50 dark:hover:bg-slate-600 cursor-pointer'
                                        }`}
                                        title={selectedBallInCourt === ALL_OPTION_VALUE
                                            ? 'Select a single drafter to enable resort'
                                            : `Compress ${selectedBallInCourt}'s ordered submittals to sequential numbers`}
                                    >
                                        {resorting ? 'Resorting\u2026' : '\u2195 Resort'}
                                    </button>
                                    )}
                                    <button
                                        onClick={handleGeneratePDF}
                                        disabled={!hasData || loading}
                                        className={`inline-flex items-center px-4 py-2 rounded-lg font-medium shadow-sm transition-all ${!hasData || loading
                                            ? 'bg-gray-300 dark:bg-slate-600 text-gray-500 dark:text-slate-400 cursor-not-allowed'
                                            : 'bg-white dark:bg-slate-700 text-accent-600 dark:text-accent-300 hover:bg-accent-50 dark:hover:bg-slate-600 cursor-pointer'
                                            }`}
                                        title="Generate PDF"
                                    >
                                        🖨️ Print/PDF
                                    </button>
                                </div>
                            </div>
                        </div>

                        {/* Tabs + Filters - fixed, do not scroll */}
                        <div className="flex-shrink-0 p-2 space-y-2">
                            {/* Tab Selection */}
                            <div className="bg-white dark:bg-slate-800 rounded-xl p-2 border border-gray-200 dark:border-slate-600 shadow-sm">
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => setSelectedTab('open')}
                                        className={`flex-1 px-4 py-2 rounded-lg font-medium transition-all ${selectedTab === 'open'
                                            ? 'bg-gradient-to-r from-accent-500 to-accent-600 text-white shadow-md'
                                            : 'bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-slate-200 hover:bg-gray-200 dark:hover:bg-slate-600'
                                            }`}
                                    >
                                        Open
                                    </button>
                                    <button
                                        onClick={() => setSelectedTab('draft')}
                                        className={`flex-1 px-4 py-2 rounded-lg font-medium transition-all ${selectedTab === 'draft'
                                            ? 'bg-gradient-to-r from-green-500 to-green-600 text-white shadow-md'
                                            : 'bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-slate-200 hover:bg-gray-200 dark:hover:bg-slate-600'
                                            }`}
                                    >
                                        Draft
                                    </button>
                                </div>
                            </div>
                            <div className={`rounded-xl p-2 border border-gray-200 dark:border-slate-600 shadow-sm ${selectedTab === 'draft' ? 'bg-gradient-to-r from-gray-50 to-green-50 dark:from-slate-700 dark:to-slate-700' : 'bg-gradient-to-r from-gray-50 to-accent-50 dark:from-slate-700 dark:to-slate-700'}`}>
                                {/* Filter header with chevron toggle */}
                                <div className="flex items-center justify-between mb-2 px-1">
                                    <span className="text-xs font-semibold text-gray-500 dark:text-slate-400">Filters</span>
                                    <button
                                        onClick={() => setIsFilterMinimized(v => !v)}
                                        className="p-1.5 rounded-lg hover:bg-gray-300 dark:hover:bg-slate-600 transition-colors"
                                        title={isFilterMinimized ? 'Expand filters' : 'Collapse filters'}
                                    >
                                        <span className="text-xl leading-none text-gray-600 dark:text-slate-300">
                                            {isFilterMinimized ? '▾' : '▴'}
                                        </span>
                                    </button>
                                </div>

                                <div className="flex flex-col gap-3">
                                    {/* Show full filter panel when expanded */}
                                    {!isFilterMinimized && (
                                        <div className="grid grid-cols-2 gap-3">
                                            <div className="flex flex-col gap-3">
                                                <FilterButtonGroup
                                                    label="🎯 Ball In Court"
                                                    options={ballInCourtOptions}
                                                    selectedValue={selectedBallInCourt}
                                                    onSelect={setSelectedBallInCourt}
                                                    allOptionValue={ALL_OPTION_VALUE}
                                                    minimized={false}
                                                />
                                                <FilterButtonGroup
                                                    label="👤 Submittal Manager"
                                                    options={submittalManagerOptions}
                                                    selectedValue={selectedSubmittalManager}
                                                    onSelect={setSelectedSubmittalManager}
                                                    allOptionValue={ALL_OPTION_VALUE}
                                                    minimized={false}
                                                />
                                            </div>
                                            <div>
                                                <FilterButtonGroup
                                                    label="📁 Project Name"
                                                    options={projectNameOptions}
                                                    selectedValue={selectedProjectName}
                                                    onSelect={setSelectedProjectName}
                                                    allOptionValue={ALL_OPTION_VALUE}
                                                    minimized={false}
                                                />
                                                <FilterButtonGroup
                                                    label="📋 Procore Status"
                                                    options={procoreStatusOptions}
                                                    selectedValue={selectedProcoreStatus}
                                                    onSelect={setSelectedProcoreStatus}
                                                    allOptionValue={ALL_OPTION_VALUE}
                                                    minimized={false}
                                                />
                                            </div>
                                        </div>
                                    )}

                                    {/* Show minimized filter labels with inline badges */}
                                    {isFilterMinimized && (
                                        <div className="flex items-center gap-4 flex-wrap text-xs">
                                            {/* Ball In Court */}
                                            <div className="flex items-center gap-1.5">
                                                <span className="font-semibold text-gray-600 dark:text-slate-300">🎯 Ball In Court</span>
                                                {selectedBallInCourt !== ALL_OPTION_VALUE && (
                                                    <span className="px-2 py-0.5 bg-accent-100 dark:bg-accent-900 text-accent-700 dark:text-accent-300 rounded-full font-medium">
                                                        {selectedBallInCourt}
                                                    </span>
                                                )}
                                            </div>
                                            {/* Submittal Manager */}
                                            <div className="flex items-center gap-1.5">
                                                <span className="font-semibold text-gray-600 dark:text-slate-300">👤 Submittal Manager</span>
                                                {selectedSubmittalManager !== ALL_OPTION_VALUE && (
                                                    <span className="px-2 py-0.5 bg-accent-100 dark:bg-accent-900 text-accent-700 dark:text-accent-300 rounded-full font-medium">
                                                        {selectedSubmittalManager}
                                                    </span>
                                                )}
                                            </div>
                                            {/* Project Name */}
                                            <div className="flex items-center gap-1.5">
                                                <span className="font-semibold text-gray-600 dark:text-slate-300">📁 Project Name</span>
                                                {selectedProjectName !== ALL_OPTION_VALUE && (
                                                    <span className="px-2 py-0.5 bg-accent-100 dark:bg-accent-900 text-accent-700 dark:text-accent-300 rounded-full font-medium">
                                                        {selectedProjectName}
                                                    </span>
                                                )}
                                            </div>
                                            {/* Procore Status */}
                                            <div className="flex items-center gap-1.5">
                                                <span className="font-semibold text-gray-600 dark:text-slate-300">📋 Procore Status</span>
                                                {selectedProcoreStatus !== ALL_OPTION_VALUE && (
                                                    <span className="px-2 py-0.5 bg-accent-100 dark:bg-accent-900 text-accent-700 dark:text-accent-300 rounded-full font-medium">
                                                        {selectedProcoreStatus}
                                                    </span>
                                                )}
                                            </div>
                                            {/* Last updated - right-aligned */}
                                            <span className="ml-auto text-gray-500 dark:text-slate-400">
                                                Last updated: <span className="font-medium text-gray-700 dark:text-slate-200">{formattedLastUpdated}</span>
                                            </span>
                                        </div>
                                    )}

                                    {/* Bottom bar (Reset, Total count) - shown when expanded */}
                                    {!isFilterMinimized && (
                                        <div className="flex items-center gap-2 pt-2">
                                            <button
                                                onClick={resetFilters}
                                                className="px-2 py-1 bg-white dark:bg-slate-600 border border-accent-300 dark:border-accent-600 text-accent-700 dark:text-accent-300 rounded text-xs font-medium shadow-sm hover:bg-accent-50 dark:hover:bg-slate-500 transition-all"
                                            >
                                                Reset Filters
                                            </button>
                                            <div className="px-2 py-1 bg-white dark:bg-slate-600 border border-gray-200 dark:border-slate-500 text-gray-600 dark:text-slate-300 rounded text-xs font-medium shadow-sm">
                                                Total: <span className="text-gray-900 dark:text-slate-100">{displayRows.length}</span> records
                                            </div>
                                            <div className="text-xs text-gray-500 dark:text-slate-400 ml-auto">
                                                Last updated: <span className="font-medium text-gray-700 dark:text-slate-200">{formattedLastUpdated}</span>
                                            </div>
                                        </div>
                                    )}
                                </div>
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

                        {!loading && !fetchError && (
                            <div className="flex-1 min-h-0 flex flex-col border border-gray-200 dark:border-slate-600 rounded-xl overflow-hidden bg-white dark:bg-slate-800 min-w-0">
                                {/* Scrollbar hidden via CSS; scroll still works with wheel/trackpad */}
                                <div
                                    ref={scrollContainerRef}
                                    className="dwl-table-scroll-hide-scrollbar flex-1 min-h-0 overflow-x-hidden"
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
                                                    const isLastBIC = column === 'LAST BIC';
                                                    const isLifespan = column === 'LIFESPAN';
                                                    const isDueDate = column === 'DUE DATE';

                                                    // Percentage widths (must total 100%). PROCORE STATUS and LAST BIC get more space.
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
                                                    } else if (isLastBIC) {
                                                        headerStyle = { width: '6%' };
                                                        columnClass = 'dwl-col-last-bic-update';
                                                    } else if (isLifespan) {
                                                        headerStyle = { width: '7%' };
                                                        columnClass = 'dwl-col-lifespan';
                                                    } else if (isDueDate) {
                                                        headerStyle = { width: '6%' };
                                                        columnClass = 'dwl-col-due-date';
                                                    } else if (isProjectName) {
                                                        headerStyle = { width: '12%' };
                                                        columnClass = 'dwl-col-name';
                                                    }

                                                    // Reduce padding for specific columns
                                                    const isLifespanHeader = column === 'LIFESPAN';
                                                    const isProjectNumberHeader = column === 'PROJ. #';
                                                    const headerPaddingClass = isOrderNumber ? 'px-0.5 py-0.5' : isLifespanHeader ? 'px-0 py-0.5' : isProjectNumberHeader ? 'px-0.5 py-0.5' : 'px-1 py-0.5';

                                                    // Determine if this column is sortable
                                                    // ORDER #, NOTES, PROCORE STATUS, COMP. STATUS are not sortable (interactive); DUE DATE is sortable (asc/desc)
                                                    const isNotSortable = isOrderNumber || isNotes || isProcoreStatus || isStatus;

                                                    // Get sort state for this column
                                                    const isSorted = columnSort.column === column;
                                                    const sortDirection = isSorted ? columnSort.direction : null;

                                                    if (isProjectName) {
                                                        return (
                                                            <th
                                                                key={column}
                                                                className="px-1 py-0.5 text-center text-xs font-bold text-gray-900 dark:text-slate-100 uppercase tracking-wider bg-gray-100 dark:bg-slate-700 border-r border-gray-300 dark:border-slate-600 dwl-col-name"
                                                                style={{ width: '12%' }}
                                                            >
                                                                <button
                                                                    onClick={handleProjectNameSortToggle}
                                                                    className="flex items-center justify-center gap-1 hover:bg-gray-200 rounded px-1 py-0.5 transition-colors w-full"
                                                                    title={
                                                                        projectNameSortMode === 'normal' ? 'Click to sort A-Z' :
                                                                            projectNameSortMode === 'a-z' ? 'Click to sort Z-A' :
                                                                                'Click to sort by Order Number'
                                                                    }
                                                                >
                                                                    <span>{column}</span>
                                                                    {projectNameSortMode === 'a-z' && <span className="text-xs">↑</span>}
                                                                    {projectNameSortMode === 'z-a' && <span className="text-xs">↓</span>}
                                                                    {projectNameSortMode === 'normal' && <span className="text-xs text-gray-400 dark:text-slate-400">↕</span>}
                                                                </button>
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
                                                            onNotesChange={canEditDrafterFields ? updateNotes : undefined}
                                                            onStatusChange={canEditDrafterFields ? updateStatus : undefined}
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

