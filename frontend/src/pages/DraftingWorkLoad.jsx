import React, { useCallback, useMemo, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDataFetching } from '../hooks/useDataFetching';
import { useMutations } from '../hooks/useMutations';
import { useFilters } from '../hooks/useFilters';
import { useDragAndDrop } from '../hooks/useDragAndDrop';
import { TableRow } from '../components/TableRow';
import { FilterButtonGroup } from '../components/FilterButtonGroup';
import { AlertMessage } from '../components/AlertMessage';
import { generateDraftingWorkLoadPDF } from '../utils/pdfUtils';
import { formatDate, formatCellValue } from '../utils/formatters';
import { checkAuth, logout } from '../utils/auth';

// Responsive column width styles for larger screens (2xl breakpoint: 1536px+)
// Laptop sizes are kept as default (max-width only), only larger screens get adjusted max-widths
const columnWidthStyles = `
    @media (min-width: 1536px) {
        /* Reduce column max-widths on very large screens to prevent bloating */
        .dwl-col-project-name { max-width: 260px !important; }
        .dwl-col-title { max-width: 250px !important; }
        .dwl-col-ball-in-court { max-width: 160px !important; }
        .dwl-col-submittal-manager { max-width: 120px !important; }
        .dwl-col-notes { max-width: 300px !important; }
        .dwl-col-submittal-id { max-width: 128px !important; }
        .dwl-col-last-bic { max-width: 100px !important; }
        .dwl-col-creation-date { max-width: 75px !important; }
    }
`;

function DraftingWorkLoad() {
    const navigate = useNavigate();
    const { submittals, columns, loading, error: fetchError, lastUpdated, refetch } = useDataFetching();
    const {
        updateOrderNumber,
        updateNotes,
        updateStatus,
        bumpSubmittal,
        updateDueDate,
    } = useMutations(refetch);

    // User admin status
    const [isAdmin, setIsAdmin] = useState(false);
    const [userLoading, setUserLoading] = useState(true);

    const handleLogout = async () => {
        await logout();
        window.location.href = '/login';
    };

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

    // Tab state: 'open' or 'draft'
    const [selectedTab, setSelectedTab] = useState('open');

    // Filter rows based on selected tab before passing to useFilters
    const filteredRowsByTab = useMemo(() => {
        return submittals.filter((row) => {
            // Filter on status field from the database
            const rowStatus = row.status ?? '';

            if (selectedTab === 'draft') {
                // Draft tab: only show submittals with status = "Draft"
                return rowStatus === 'Draft';
            } else {
                // Open tab: show all submittals except those with status = "Draft"
                return rowStatus !== 'Draft';
            }
        });
    }, [submittals, selectedTab]);

    const rows = filteredRowsByTab; // now that submittals is clean, we alias

    // Use the filters hook
    const {
        selectedBallInCourt,
        selectedSubmittalManager,
        selectedProjectName,
        projectNameSortMode,
        columnSort,
        setSelectedBallInCourt,
        setSelectedSubmittalManager,
        setSelectedProjectName,
        ballInCourtOptions,
        submittalManagerOptions,
        projectNameOptions,
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


    const formattedLastUpdated = useMemo(
        () => lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Unknown',
        [lastUpdated]
    );

    const hasData = displayRows.length > 0;
    const visibleColumns = columns.filter(column => column !== 'Submittals Id');
    const tableColumnCount = visibleColumns.length;

    return (
        <>
            <style>{columnWidthStyles}</style>
            {/* Navigation Header - Always visible for navigation */}
            <div className="w-full bg-white/95 backdrop-blur-sm shadow-md border-b border-gray-200 sticky top-0 z-50" style={{ width: '100%', minWidth: '100%' }}>
                <div className="max-w-full mx-auto px-4 py-3 w-full" style={{ width: '100%' }}>
                    <div className="flex items-center justify-between">
                        <div
                            className="text-xl font-bold bg-gradient-to-r from-accent-500 to-accent-600 bg-clip-text text-transparent cursor-pointer hover:from-accent-600 hover:to-accent-700 transition-all"
                            onClick={() => navigate('/')}
                        >
                            ← Back to Dashboard
                        </div>
                        <div className="flex items-center gap-3">
                            <button
                                onClick={() => navigate('/')}
                                className="px-4 py-2 rounded-lg font-medium transition-all duration-200 text-gray-700 hover:bg-gray-100"
                            >
                                Dashboard
                            </button>
                            <button
                                onClick={handleLogout}
                                className="px-4 py-2 rounded-lg font-medium transition-all duration-200 text-red-600 hover:bg-red-50 border border-red-200"
                            >
                                Logout
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            <div className="w-full min-h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-2 px-2" style={{ width: '100%', minWidth: '100%' }}>
                <div className="max-w-full mx-auto w-full" style={{ width: '100%' }}>
                    <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
                        <div className={`px-4 py-3 ${selectedTab === 'draft' ? 'bg-gradient-to-r from-green-500 to-green-600' : 'bg-gradient-to-r from-accent-500 to-accent-600'}`}>
                            <div className="flex items-center justify-between">
                                <div>
                                    <h1 className="text-3xl font-bold text-white">Drafting Work Load</h1>

                                </div>
                                <div className="flex items-center gap-3">
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

                        <div className="p-2 space-y-2">
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

                            {loading && (
                                <div className="text-center py-12">
                                    <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                                    <p className="text-gray-600 font-medium">Loading Drafting Work Load data...</p>
                                </div>
                            )}

                            {fetchError && !loading && (
                                <AlertMessage
                                    type="error"
                                    title="Unable to load Drafting Work Load data"
                                    message={fetchError}
                                />
                            )}

                            {!loading && !fetchError && (
                                <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
                                    <div className="">
                                        <table className="w-full" style={{ borderCollapse: 'collapse', width: '100%' }}>
                                            <thead className="bg-gray-100">
                                                <tr>
                                                    {visibleColumns.map((column) => {
                                                        const isOrderNumber = column === 'Order Number';
                                                        const isNotes = column === 'Notes';
                                                        const isProjectName = column === 'Project Name';
                                                        const isTitle = column === 'Title';
                                                        const isStatus = column === 'Status';
                                                        const isBallInCourt = column === 'Ball In Court';
                                                        const isType = column === 'Type';
                                                        const isSubmittalId = column === 'Submittals Id';
                                                        const isProjectNumber = column === 'Project Number';
                                                        const isSubmittalManager = column === 'Submittal Manager';
                                                        const isLastBIC = column === 'Last BIC';
                                                        const isCreationDate = column === 'Creation Date';
                                                        const isDueDate = column === 'Due Date';

                                                        // Set max-widths for all columns (perfect for laptop screens)
                                                        // CSS media queries handle larger screens to prevent bloating
                                                        let headerStyle = {};
                                                        let columnClass = '';
                                                        if (isOrderNumber) {
                                                            headerStyle = { maxWidth: '64px' };
                                                            columnClass = 'dwl-col-order-number';
                                                        } else if (isSubmittalId) {
                                                            headerStyle = { maxWidth: '128px' };
                                                            columnClass = 'dwl-col-submittal-id';
                                                        } else if (isProjectNumber) {
                                                            headerStyle = { maxWidth: '65px' };
                                                            columnClass = 'dwl-col-project-number';
                                                        } else if (isTitle) {
                                                            headerStyle = { maxWidth: '280px' };
                                                            columnClass = 'dwl-col-title';
                                                        } else if (isNotes) {
                                                            headerStyle = { maxWidth: '350px' };
                                                            columnClass = 'dwl-col-notes';
                                                        } else if (isBallInCourt) {
                                                            headerStyle = { maxWidth: '180px' };
                                                            columnClass = 'dwl-col-ball-in-court';
                                                        } else if (isType) {
                                                            headerStyle = { maxWidth: '80px' };
                                                            columnClass = 'dwl-col-type';
                                                        } else if (isStatus) {
                                                            headerStyle = { maxWidth: '96px' };
                                                            columnClass = 'dwl-col-status';
                                                        } else if (isSubmittalManager) {
                                                            headerStyle = { maxWidth: '128px' };
                                                            columnClass = 'dwl-col-submittal-manager';
                                                        } else if (isLastBIC) {
                                                            headerStyle = { maxWidth: '100px' };
                                                            columnClass = 'dwl-col-last-bic';
                                                        } else if (isCreationDate) {
                                                            headerStyle = { maxWidth: '75px' };
                                                            columnClass = 'dwl-col-creation-date';
                                                        } else if (isDueDate) {
                                                            headerStyle = { maxWidth: '120px' };
                                                            columnClass = 'dwl-col-due-date';
                                                        }

                                                        // Reduce padding for specific columns
                                                        const isCreationDateHeader = column === 'Creation Date';
                                                        const isProjectNumberHeader = column === 'Project Number';
                                                        const headerPaddingClass = isOrderNumber ? 'px-0.5 py-0.5' : isCreationDateHeader ? 'px-0 py-0.5' : isProjectNumberHeader ? 'px-0.5 py-0.5' : 'px-1 py-0.5';

                                                        // Determine if this column is sortable
                                                        // Order Number, Notes, Status, and Due Date are not sortable (they're interactive)
                                                        const isNotSortable = isOrderNumber || isNotes || isStatus || isDueDate;

                                                        // Get sort state for this column
                                                        const isSorted = columnSort.column === column;
                                                        const sortDirection = isSorted ? columnSort.direction : null;

                                                        if (isProjectName) {
                                                            return (
                                                                <th
                                                                    key={column}
                                                                    className="px-1 py-0.5 text-center text-xs font-bold text-gray-900 uppercase tracking-wider bg-gray-100 border-r border-gray-300 dwl-col-project-name"
                                                                    style={{ maxWidth: '280px' }}
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

                                                        // Non-sortable column (Order Number, Notes, Status, Due Date)
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
            </div>
        </>
    );
}

export default DraftingWorkLoad;

