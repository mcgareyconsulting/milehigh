import React, { useCallback, useMemo, useState, useEffect } from 'react';
import { useDataFetching } from '../hooks/useDataFetching';
import { useMutations } from '../hooks/useMutations';
import { useFilters } from '../hooks/useFilters';
import { useDragAndDrop } from '../hooks/useDragAndDrop';
import { TableRow } from '../components/TableRow';
import { FilterButtonGroup } from '../components/FilterButtonGroup';
import { AlertMessage } from '../components/AlertMessage';
import { generateDraftingWorkLoadPDF } from '../utils/pdfUtils';
import { formatDate, formatCellValue } from '../utils/formatters';
import { checkAuth } from '../utils/auth';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';

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
    const [locationEnabled, setLocationEnabled] = useState(false);
    const [userCoords, setUserCoords] = useState(null);
    const [locationRequesting, setLocationRequesting] = useState(false);
    const locationFilter = locationEnabled && userCoords ? userCoords : null;
    // Tab state: 'open' or 'draft' — passed to API so backend returns tab-specific submittals
    const [selectedTab, setSelectedTab] = useState('open');
    const { submittals, columns, loading, error: fetchError, lastUpdated, refetch } = useDataFetching(locationFilter, selectedTab);
    const {
        updateOrderNumber,
        updateNotes,
        updateStatus,
        updateProcoreStatus,
        bumpSubmittal,
        updateDueDate,
    } = useMutations(refetch);

    // Submittal statuses for company (Procore status dropdown on draft tab)
    const [submittalStatuses, setSubmittalStatuses] = useState([]);
    useEffect(() => {
        draftingWorkLoadApi.fetchSubmittalStatuses()
            .then(setSubmittalStatuses)
            .catch((err) => console.error('Failed to fetch submittal statuses:', err));
    }, []);

    // User admin status
    const [isAdmin, setIsAdmin] = useState(false);
    const [userLoading, setUserLoading] = useState(true);

    // Fetch user info to check admin status
    useEffect(() => {
        const fetchUserInfo = async () => {
            try {
                const user = await checkAuth();
                setIsAdmin(user?.is_admin || false);
            } catch (err) {
                console.error('Error fetching user info:', err);
                setIsAdmin(false);
            } finally {
                setUserLoading(false);
            }
        };
        fetchUserInfo();
    }, []);

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

    // Drag and drop functionality
    const {
        draggedIndex,
        dragOverIndex,
        handleDragStart,
        handleDragOver,
        handleDragLeave,
        handleDrop,
    } = useDragAndDrop(rows, displayRows, updateOrderNumber);


    const handleGeneratePDF = useCallback(() => {
        generateDraftingWorkLoadPDF(displayRows, columns, lastUpdated);
    }, [displayRows, columns, lastUpdated]);

    const handleLocationToggle = useCallback(() => {
        if (locationEnabled) {
            setLocationEnabled(false);
            setUserCoords(null);
            return;
        }
        setLocationRequesting(true);
        if (!navigator.geolocation) {
            setLocationRequesting(false);
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (position) => {
                setUserCoords({ lat: position.coords.latitude, lng: position.coords.longitude });
                setLocationEnabled(true);
                setLocationRequesting(false);
                // Do not refetch here: ref is still null until next render. The effect in
                // useDataFetching will refetch when locationFilter (and ref) update.
            },
            () => {
                setLocationRequesting(false);
                setLocationEnabled(false);
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }, [locationEnabled, refetch]);


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
            <div className="w-full h-full flex flex-col bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50" style={{ width: '100%', minWidth: '100%' }}>
                <div className="flex-1 min-h-0 max-w-full mx-auto w-full py-2 px-2 flex flex-col" style={{ width: '100%' }}>
                    <div className="bg-white rounded-2xl shadow-xl overflow-hidden flex flex-col flex-1 min-h-0">
                        {/* Title bar - fixed, does not scroll */}
                        <div className={`flex-shrink-0 px-4 py-3 ${selectedTab === 'draft' ? 'bg-gradient-to-r from-green-500 to-green-600' : 'bg-gradient-to-r from-accent-500 to-accent-600'}`}>
                            <div className="flex items-center justify-between">
                                <div>
                                    <h1 className="text-3xl font-bold text-white">Drafting Work Load</h1>
                                </div>
                                <div className="flex items-center gap-3">
                                    <button
                                        type="button"
                                        onClick={handleLocationToggle}
                                        disabled={locationRequesting}
                                        className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg font-medium shadow-sm transition-all ${locationEnabled
                                            ? 'bg-green-500 text-white hover:bg-green-600'
                                            : 'bg-white text-gray-800 hover:bg-gray-50'
                                            } ${locationRequesting ? 'opacity-70 cursor-wait' : 'cursor-pointer'}`}
                                        title={locationEnabled ? 'Turn off location filter' : 'Filter submittals by your current location (job site)'}
                                    >
                                        {locationRequesting ? (
                                            <>
                                                <span className="inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                                                Location…
                                            </>
                                        ) : locationEnabled ? (
                                            <>📍 Filtering by location</>
                                        ) : (
                                            <>📍 Use my location</>
                                        )}
                                    </button>
                                    <button
                                        onClick={handleGeneratePDF}
                                        disabled={!hasData || loading}
                                        className={`inline-flex items-center px-4 py-2 rounded-lg font-medium shadow-sm transition-all ${!hasData || loading
                                            ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                            : 'bg-white text-accent-600 hover:bg-accent-50 cursor-pointer'
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
                            <div className="bg-white rounded-xl p-2 border border-gray-200 shadow-sm">
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => setSelectedTab('open')}
                                        className={`flex-1 px-4 py-2 rounded-lg font-medium transition-all ${selectedTab === 'open'
                                            ? 'bg-gradient-to-r from-accent-500 to-accent-600 text-white shadow-md'
                                            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                            }`}
                                    >
                                        Open
                                    </button>
                                    <button
                                        onClick={() => setSelectedTab('draft')}
                                        className={`flex-1 px-4 py-2 rounded-lg font-medium transition-all ${selectedTab === 'draft'
                                            ? 'bg-gradient-to-r from-green-500 to-green-600 text-white shadow-md'
                                            : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                                            }`}
                                    >
                                        Draft
                                    </button>
                                </div>
                            </div>
                            <div className={`rounded-xl p-2 border border-gray-200 shadow-sm ${selectedTab === 'draft' ? 'bg-gradient-to-r from-gray-50 to-green-50' : 'bg-gradient-to-r from-gray-50 to-accent-50'}`}>
                                <div className="flex flex-col gap-3">
                                    <div className="grid grid-cols-2 gap-3">
                                        <div className="flex flex-col gap-3">
                                            <FilterButtonGroup
                                                label="🎯 Ball In Court"
                                                options={ballInCourtOptions}
                                                selectedValue={selectedBallInCourt}
                                                onSelect={setSelectedBallInCourt}
                                                allOptionValue={ALL_OPTION_VALUE}
                                            />
                                            <FilterButtonGroup
                                                label="👤 Submittal Manager"
                                                options={submittalManagerOptions}
                                                selectedValue={selectedSubmittalManager}
                                                onSelect={setSelectedSubmittalManager}
                                                allOptionValue={ALL_OPTION_VALUE}
                                            />
                                        </div>
                                        <div>
                                            <FilterButtonGroup
                                                label="📁 Project Name"
                                                options={projectNameOptions}
                                                selectedValue={selectedProjectName}
                                                onSelect={setSelectedProjectName}
                                                allOptionValue={ALL_OPTION_VALUE}
                                            />
                                            <FilterButtonGroup
                                                label="📋 Procore Status"
                                                options={procoreStatusOptions}
                                                selectedValue={selectedProcoreStatus}
                                                onSelect={setSelectedProcoreStatus}
                                                allOptionValue={ALL_OPTION_VALUE}
                                            />
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2 pt-2">
                                        <button
                                            onClick={resetFilters}
                                            className="px-2 py-1 bg-white border border-accent-300 text-accent-700 rounded text-xs font-medium shadow-sm hover:bg-accent-50 transition-all"
                                        >
                                            Reset Filters
                                        </button>
                                        <div className="px-2 py-1 bg-white border border-gray-200 text-gray-600 rounded text-xs font-medium shadow-sm">
                                            Total: <span className="text-gray-900">{displayRows.length}</span> records
                                        </div>
                                        <div className="text-xs text-gray-500 ml-auto">
                                            Last updated: <span className="font-medium text-gray-700">{formattedLastUpdated}</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {loading && (
                            <div className="flex-shrink-0 text-center py-12">
                                <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                                <p className="text-gray-600 font-medium">Loading Drafting Work Load data...</p>
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

                        {!loading && !fetchError && (
                            <div className="flex-1 min-h-0 flex flex-col border border-gray-200 rounded-xl overflow-hidden bg-white min-w-0">
                                {/* Scrollbar hidden via CSS; scroll still works with wheel/trackpad */}
                                <div
                                    className="dwl-table-scroll-hide-scrollbar flex-1 min-h-0 overflow-x-hidden"
                                    style={{ overflowY: 'auto' }}
                                >
                                    <table className="w-full" style={{ borderCollapse: 'collapse', width: '100%', tableLayout: 'fixed' }}>
                                        <thead className="sticky top-0 z-10 bg-gray-100 shadow-sm">
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
                                                                className="px-1 py-0.5 text-center text-xs font-bold text-gray-900 uppercase tracking-wider bg-gray-100 border-r border-gray-300 dwl-col-name"
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
                                                                    {projectNameSortMode === 'normal' && <span className="text-xs text-gray-400">↕</span>}
                                                                </button>
                                                            </th>
                                                        );
                                                    }

                                                    // Render sortable column header
                                                    if (!isNotSortable) {
                                                        return (
                                                            <th
                                                                key={column}
                                                                className={`${headerPaddingClass} text-center text-xs font-bold text-gray-900 uppercase tracking-wider bg-gray-100 border-r border-gray-300 ${columnClass}`}
                                                                style={headerStyle}
                                                            >
                                                                <button
                                                                    onClick={() => handleColumnSort(column)}
                                                                    className="flex items-center justify-center gap-1 hover:bg-gray-200 rounded px-1 py-0.5 transition-colors w-full"
                                                                    title={
                                                                        sortDirection === null ? 'Click to sort ascending' :
                                                                            sortDirection === 'asc' ? 'Click to sort descending' :
                                                                                'Click to remove sort'
                                                                    }
                                                                >
                                                                    <span>{column}</span>
                                                                    {sortDirection === 'asc' && <span className="text-xs">↑</span>}
                                                                    {sortDirection === 'desc' && <span className="text-xs">↓</span>}
                                                                    {sortDirection === null && <span className="text-xs text-gray-400">↕</span>}
                                                                </button>
                                                            </th>
                                                        );
                                                    }

                                                    // Non-sortable column (Order Number, Notes, Procore Status, Comp. Status)
                                                    return (
                                                        <th
                                                            key={column}
                                                            className={`${headerPaddingClass} text-center text-xs font-bold text-gray-900 uppercase tracking-wider bg-gray-100 border-r border-gray-300 ${columnClass}`}
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
                                                        className="px-6 py-12 text-center text-gray-500 font-medium bg-white rounded-md"
                                                    >
                                                        No records match the selected filters.
                                                    </td>
                                                </tr>
                                            ) : (
                                                displayRows.map((row, index) => (
                                                    <TableRow
                                                        key={row.id}
                                                        row={row}
                                                        columns={columns}
                                                        formatCellValue={formatCellValue}
                                                        formatDate={formatDate}
                                                        onOrderNumberChange={isAdmin ? updateOrderNumber : undefined}
                                                        onNotesChange={isAdmin ? updateNotes : undefined}
                                                        onStatusChange={isAdmin ? updateStatus : undefined}
                                                        onProcoreStatusChange={isAdmin ? updateProcoreStatus : undefined}
                                                        procoreStatusOptions={submittalStatuses}
                                                        selectedTab={selectedTab}
                                                        onBump={isAdmin ? bumpSubmittal : undefined}
                                                        onDueDateChange={isAdmin ? updateDueDate : undefined}
                                                        rowIndex={index}
                                                        onDragStart={isAdmin ? handleDragStart : undefined}
                                                        onDragOver={isAdmin ? handleDragOver : undefined}
                                                        onDragLeave={isAdmin ? handleDragLeave : undefined}
                                                        onDrop={isAdmin ? handleDrop : undefined}
                                                        isDragging={draggedIndex}
                                                        dragOverIndex={dragOverIndex}
                                                        isAdmin={isAdmin}
                                                    />
                                                ))
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </>
    );
}

export default DraftingWorkLoad;

