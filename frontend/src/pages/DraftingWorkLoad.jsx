import React, { useEffect, useCallback, useMemo } from 'react';
import { useDataFetching } from '../hooks/useDataFetching';
import { useMutations } from '../hooks/useMutations';
import { useFilters } from '../hooks/useFilters';
import { useDragAndDrop } from '../hooks/useDragAndDrop';
import { TableRow } from '../components/TableRow';
import { FilterButtonGroup } from '../components/FilterButtonGroup';
import { AlertMessage } from '../components/AlertMessage';
import { generateDraftingWorkLoadPDF } from '../utils/pdfUtils';
import { formatDate, formatCellValue } from '../utils/formatters';

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
    }
`;

function DraftingWorkLoad() {
    const { submittals, columns, loading, error: fetchError, lastUpdated, refetch } = useDataFetching();
    const {
        updateOrderNumber,
        updateNotes,
        updateStatus,
        uploadFile,
        uploading,
        uploadError,
        uploadSuccess,
        clearUploadSuccess,
    } = useMutations(refetch);

    const rows = submittals; // now that submittals is clean, we alias

    // Use the filters hook
    const {
        selectedBallInCourt,
        selectedSubmittalManager,
        selectedProjectName,
        projectNameSortMode,
        setSelectedBallInCourt,
        setSelectedSubmittalManager,
        setSelectedProjectName,
        ballInCourtOptions,
        submittalManagerOptions,
        projectNameOptions,
        displayRows,
        resetFilters,
        handleProjectNameSortToggle,
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

    const handleFileUpload = async (event) => {
        const file = event.target.files[0];
        if (!file) {
            return;
        }

        await uploadFile(file);

        // Reset file input
        event.target.value = '';
    };

    // Clear upload success message after 3 seconds
    useEffect(() => {
        if (uploadSuccess) {
            const timer = setTimeout(() => {
                clearUploadSuccess();
            }, 3000);
            return () => clearTimeout(timer);
        }
    }, [uploadSuccess, clearUploadSuccess]);


    const formattedLastUpdated = useMemo(
        () => lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Unknown',
        [lastUpdated]
    );

    const hasData = displayRows.length > 0;
    const tableColumnCount = columns.length;

    return (
        <>
            <style>{columnWidthStyles}</style>
            <div className="w-full min-h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-2 px-2" style={{ width: '100%', minWidth: '100%' }}>
                <div className="max-w-full mx-auto w-full" style={{ width: '100%' }}>
                    <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
                        <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-4 py-3">
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
                                    <label className="relative cursor-pointer">
                                        <input
                                            type="file"
                                            accept=".xlsx,.xls"
                                            onChange={handleFileUpload}
                                            disabled={uploading}
                                            className="hidden"
                                            id="file-upload"
                                        />
                                        <span className={`inline-flex items-center px-4 py-2 rounded-lg font-medium shadow-sm transition-all ${uploading
                                            ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                            : 'bg-white text-accent-600 hover:bg-accent-50 cursor-pointer'
                                            }`}>
                                            {uploading ? (
                                                <>
                                                    <span className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-accent-600 mr-2"></span>
                                                    Uploading...
                                                </>
                                            ) : (
                                                <>
                                                    📤 Upload Excel
                                                </>
                                            )}
                                        </span>
                                    </label>
                                </div>
                            </div>
                        </div>

                        <div className="p-2 space-y-2">
                            <div className="bg-gradient-to-r from-gray-50 to-accent-50 rounded-xl p-2 border border-gray-200 shadow-sm">
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
                                {uploadSuccess && (
                                    <AlertMessage
                                        type="success"
                                        title="File uploaded successfully!"
                                        message="The data has been refreshed."
                                    />
                                )}
                                {uploadError && (
                                    <AlertMessage
                                        type="error"
                                        title="Upload failed"
                                        message={uploadError}
                                    />
                                )}
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
                                                    {columns.map((column) => {
                                                        const isOrderNumber = column === 'Order Number';
                                                        const isNotes = column === 'Notes';
                                                        const isProjectName = column === 'Project Name';
                                                        const isTitle = column === 'Title';

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

                                                        const isStatus = column === 'Status';
                                                        const isBallInCourt = column === 'Ball In Court';
                                                        const isType = column === 'Type';
                                                        const isSubmittalId = column === 'Submittals Id';
                                                        const isProjectNumber = column === 'Project Number';
                                                        const isSubmittalManager = column === 'Submittal Manager';

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
                                                            headerStyle = { maxWidth: '80px' };
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
                                                        }

                                                        return (
                                                            <th
                                                                key={column}
                                                                className={`${isOrderNumber ? 'px-0.5 py-0.5' : 'px-1 py-0.5'} text-center text-xs font-bold text-gray-900 uppercase tracking-wider bg-gray-100 border-r border-gray-300 ${columnClass}`}
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
                                                            onOrderNumberChange={updateOrderNumber}
                                                            onNotesChange={updateNotes}
                                                            onStatusChange={updateStatus}
                                                            rowIndex={index}
                                                            onDragStart={handleDragStart}
                                                            onDragOver={handleDragOver}
                                                            onDragLeave={handleDragLeave}
                                                            onDrop={handleDrop}
                                                            isDragging={draggedIndex}
                                                            dragOverIndex={dragOverIndex}
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

