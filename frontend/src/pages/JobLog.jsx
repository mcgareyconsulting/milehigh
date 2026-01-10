import React, { useMemo, useEffect, useState } from 'react';
import { useJobsDataFetching } from '../hooks/useJobsDataFetching';
import { useJobsFilters } from '../hooks/useJobsFilters';
import { JobsTableRow } from '../components/JobsTableRow';
import { jobsApi } from '../services/jobsApi';

function JobLog() {
    const { jobs, columns, loading, error: fetchError, lastUpdated, refetch, fetchAll } = useJobsDataFetching();
    const [showReleaseModal, setShowReleaseModal] = useState(false);
    const [csvData, setCsvData] = useState('');
    const [parsedPreview, setParsedPreview] = useState(null);
    const [releasing, setReleasing] = useState(false);
    const [releaseError, setReleaseError] = useState(null);
    const [releaseSuccess, setReleaseSuccess] = useState(null);

    // Use the filters hook
    const {
        selectedProjectName,
        selectedStages,
        jobNumberSearch,
        releaseNumberSearch,
        setSelectedProjectName,
        setSelectedStages,
        setJobNumberSearch,
        setReleaseNumberSearch,
        projectNameOptions,
        sortBy,
        showNotComplete,
        showNotShippingComplete,
        showBeforePaintComplete,
        setSortBy,
        setShowNotComplete,
        setShowNotShippingComplete,
        setShowBeforePaintComplete,
        stageOptions,
        stageColors,
        displayJobs,
        resetFilters,
        toggleStage,
        ALL_OPTION_VALUE,
    } = useJobsFilters(jobs);

    const formatDate = (dateValue) => {
        if (!dateValue) return '—';
        try {
            const date = new Date(dateValue);
            if (isNaN(date.getTime())) return '—';
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const year = String(date.getFullYear()).slice(-2);
            return `${month}/${day}/${year}`;
        } catch (e) {
            return '—';
        }
    };

    const formatCellValue = (value, columnName) => {
        if (value === null || value === undefined || value === '') {
            return '—';
        }
        if (Array.isArray(value)) {
            return value.join(', ');
        }
        // Format Fab Hrs and Install HRS to 2 decimal places
        if (columnName === 'Fab Hrs' || columnName === 'Install HRS') {
            const numValue = parseFloat(value);
            if (!isNaN(numValue)) {
                return numValue.toFixed(2);
            }
        }
        return value;
    };

    const formattedLastUpdated = lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Unknown';

    // Check if we have data to display
    // Only show "No records found" if we've finished loading and have no jobs at all
    // If we have jobs but displayJobs is empty, that means filters are excluding everything
    const hasData = displayJobs.length > 0;
    const hasJobsData = !loading && jobs.length > 0;

    // Define column order explicitly
    const columnOrder = [
        'Job #',
        'Release #',
        'Job',
        'Description',
        'Fab Hrs',
        'Install HRS',
        'Paint color',
        'PM',
        'BY',
        'Released',
        'Fab Order',
        'Stage',
        'Start install',
        'Comp. ETA',
        'Job Comp',
        'Invoiced',
        'Notes'
    ];

    // Filter and order columns based on defined order
    const columnHeaders = useMemo(() => {
        // Only include columns that exist in the data and are in our defined order
        return columnOrder.filter(col => columns.includes(col));
    }, [columns]);

    const tableColumnCount = columnHeaders.length;

    const handleReleaseClick = () => {
        setShowReleaseModal(true);
        setCsvData('');
        setParsedPreview(null);
        setReleaseError(null);
        setReleaseSuccess(null);
    };

    const handleCloseModal = () => {
        setShowReleaseModal(false);
        setCsvData('');
        setParsedPreview(null);
        setReleaseError(null);
        setReleaseSuccess(null);
    };

    const parsePreviewData = (data) => {
        if (!data || !data.trim()) {
            setParsedPreview(null);
            return;
        }

        try {
            // Detect delimiter
            const firstLine = data.split('\n')[0];
            const delimiter = firstLine.includes('\t') ? '\t' : ',';

            // Parse rows
            const lines = data.split('\n').filter(line => line.trim());
            const expectedColumns = [
                'Job #', 'Release #', 'Job', 'Description', 'Fab Hrs',
                'Install HRS', 'Paint color', 'PM', 'BY', 'Released', 'Fab Order'
            ];

            // Check if first row is headers
            let startIdx = 0;
            const firstRow = lines[0].split(delimiter);
            if (firstRow.length === expectedColumns.length) {
                // Check if it looks like headers
                const firstRowLower = firstRow.map(cell => cell.toLowerCase().trim());
                const hasHeaderKeywords = expectedColumns.some((col, idx) =>
                    col.toLowerCase().includes(firstRowLower[idx]) ||
                    firstRowLower[idx].includes(col.toLowerCase().split(' ')[0])
                );
                if (hasHeaderKeywords) {
                    startIdx = 1;
                }
            }

            // Parse data rows
            const parsedRows = [];
            for (let i = startIdx; i < lines.length; i++) {
                const cells = lines[i].split(delimiter);
                if (cells.length === 0 || cells.every(cell => !cell.trim())) continue;

                // Pad with empty strings if needed
                while (cells.length < expectedColumns.length) {
                    cells.push('');
                }

                const row = {};
                expectedColumns.forEach((col, idx) => {
                    row[col] = cells[idx] ? cells[idx].trim() : '';
                });
                parsedRows.push(row);
            }

            setParsedPreview(parsedRows.length > 0 ? parsedRows : null);
        } catch (error) {
            console.error('Error parsing preview:', error);
            setParsedPreview(null);
        }
    };

    const handleCsvDataChange = (e) => {
        const value = e.target.value;
        setCsvData(value);
        parsePreviewData(value);
    };

    const handleReleaseSubmit = async () => {
        if (!csvData.trim()) {
            setReleaseError('Please paste CSV data');
            return;
        }

        setReleasing(true);
        setReleaseError(null);
        setReleaseSuccess(null);

        try {
            const result = await jobsApi.releaseJobData(csvData);
            setReleaseSuccess({
                processed: result.processed_count || 0,
                created: result.created_count || 0,
                updated: result.updated_count || 0,
                errors: result.error_count || 0
            });

            // Refresh the job data
            await fetchAll();

            // Auto-close modal after 3 seconds
            setTimeout(() => {
                handleCloseModal();
            }, 3000);
        } catch (error) {
            setReleaseError(error.message || 'Failed to release job data');
        } finally {
            setReleasing(false);
        }
    };

    return (
        <div className="w-full min-h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-8 px-4" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-[95%] mx-auto w-full" style={{ width: '100%' }}>
                <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
                    <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-8 py-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <h1 className="text-3xl font-bold text-white">Job Log 2.0</h1>
                                <img
                                    src="/bananas-svgrepo-com.svg"
                                    alt="banana"
                                    className="w-7 h-7"
                                    style={{ filter: 'brightness(0) invert(1)' }}
                                />
                            </div>
                            <button
                                onClick={handleReleaseClick}
                                className="px-4 py-2 bg-white text-accent-600 rounded-lg font-medium shadow-sm hover:bg-accent-50 transition-all flex items-center gap-2"
                            >
                                📋 Release
                            </button>
                        </div>
                    </div>

                    <div className="p-6 space-y-4">
                        <div className="bg-gradient-to-r from-gray-50 to-accent-50 rounded-xl p-4 border border-gray-200 shadow-sm">
                            <div className="grid grid-cols-2 grid-rows-2 gap-6">
                                {/* Top Left: Project Name */}
                                <div>
                                    <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                        Project Name
                                    </label>
                                    <div className="grid grid-cols-10 gap-0.5">
                                        <button
                                            onClick={() => setSelectedProjectName(ALL_OPTION_VALUE)}
                                            className={`px-0.5 py-0.5 rounded text-[9px] font-medium shadow-sm transition-all truncate ${selectedProjectName === ALL_OPTION_VALUE
                                                ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                }`}
                                            title="All"
                                        >
                                            All
                                        </button>
                                        {projectNameOptions.map((option) => (
                                            <button
                                                key={option}
                                                onClick={() => setSelectedProjectName(option)}
                                                className={`px-0.5 py-0.5 rounded text-[9px] font-medium shadow-sm transition-all truncate ${selectedProjectName === option
                                                    ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                    : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                    }`}
                                                title={option}
                                            >
                                                {option.length > 8 ? option.substring(0, 8) + '...' : option}
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                {/* Top Right: Status Filters */}
                                <div>
                                    <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                        Filters
                                    </label>
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <button
                                            onClick={() => setSortBy(sortBy === 'fab_order_asc' ? 'default' : 'fab_order_asc')}
                                            className={`px-3 py-1.5 rounded text-xs font-medium shadow-sm transition-all whitespace-nowrap min-w-[140px] text-center ${sortBy === 'fab_order_asc'
                                                ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                }`}
                                        >
                                            Sort by Fab Order {sortBy === 'fab_order_asc' && '↑'}
                                        </button>
                                        <button
                                            onClick={() => {
                                                const newValue = !showNotComplete;
                                                setShowNotComplete(newValue);
                                                // When activating, turn off other status filters and sort by fab order ascending
                                                if (newValue) {
                                                    setShowNotShippingComplete(false);
                                                    setShowBeforePaintComplete(false);
                                                    setSortBy('fab_order_asc');
                                                }
                                            }}
                                            className={`px-3 py-1.5 rounded text-xs font-medium shadow-sm transition-all whitespace-nowrap min-w-[140px] text-center ${showNotComplete
                                                ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                }`}
                                        >
                                            All Not Complete
                                        </button>
                                        <button
                                            onClick={() => {
                                                const newValue = !showNotShippingComplete;
                                                setShowNotShippingComplete(newValue);
                                                // When activating, turn off other status filters and sort by fab order ascending
                                                if (newValue) {
                                                    setShowNotComplete(false);
                                                    setShowBeforePaintComplete(false);
                                                    setSortBy('fab_order_asc');
                                                }
                                            }}
                                            className={`px-3 py-1.5 rounded text-xs font-medium shadow-sm transition-all whitespace-nowrap min-w-[140px] text-center ${showNotShippingComplete
                                                ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                }`}
                                        >
                                            Not Shipping Complete
                                        </button>
                                        <button
                                            onClick={() => {
                                                const newValue = !showBeforePaintComplete;
                                                setShowBeforePaintComplete(newValue);
                                                // When activating, turn off other status filters and sort by fab order ascending
                                                if (newValue) {
                                                    setShowNotComplete(false);
                                                    setShowNotShippingComplete(false);
                                                    setSortBy('fab_order_asc');
                                                }
                                            }}
                                            className={`px-3 py-1.5 rounded text-xs font-medium shadow-sm transition-all whitespace-nowrap min-w-[140px] text-center ${showBeforePaintComplete
                                                ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                }`}
                                        >
                                            Before Paint Complete
                                        </button>
                                    </div>
                                </div>

                                {/* Bottom Left: Reset Filters, Job #, Release # */}
                                <div className="flex items-center gap-2 flex-wrap">
                                    <button
                                        onClick={resetFilters}
                                        className="px-3 py-1.5 bg-white border border-accent-300 text-accent-700 rounded text-xs font-medium shadow-sm hover:bg-accent-50 transition-all whitespace-nowrap"
                                    >
                                        Reset Filters
                                    </button>
                                    <div className="flex items-center gap-2">
                                        <label className="text-xs font-semibold text-gray-700 whitespace-nowrap">
                                            Job #:
                                        </label>
                                        <input
                                            type="text"
                                            value={jobNumberSearch}
                                            onChange={(e) => setJobNumberSearch(e.target.value)}
                                            placeholder="Job #..."
                                            className="w-24 px-2 py-1 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500 bg-white text-gray-900"
                                        />
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <label className="text-xs font-semibold text-gray-700 whitespace-nowrap">
                                            Release #:
                                        </label>
                                        <input
                                            type="text"
                                            value={releaseNumberSearch}
                                            onChange={(e) => setReleaseNumberSearch(e.target.value)}
                                            placeholder="Release #..."
                                            className="w-24 px-2 py-1 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500 bg-white text-gray-900"
                                        />
                                    </div>
                                </div>

                                {/* Bottom Right: Total records and Last updated */}
                                <div className="flex items-center justify-end gap-4">
                                    <div className="px-2 py-1 bg-white border border-gray-200 text-gray-600 rounded text-xs font-medium shadow-sm">
                                        Total: <span className="text-gray-900">{displayJobs.length}</span> records
                                    </div>
                                    <div className="text-xs text-gray-500">
                                        Last updated: <span className="font-medium text-gray-700">{formattedLastUpdated}</span>
                                    </div>
                                </div>
                            </div>
                        </div>



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

                        {!loading && !fetchError && (
                            <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
                                <div className="overflow-x-auto">
                                    <table className="w-full" style={{ borderCollapse: 'collapse' }}>
                                        <thead className="bg-gray-100">
                                            <tr>
                                                {columnHeaders.map((column) => {
                                                    const isReleaseNumber = column === 'Release #';
                                                    // Display "rel. #" for Release # column header
                                                    const displayHeader = column === 'Release #' ? 'rel. #' : column;
                                                    return (
                                                        <th
                                                            key={column}
                                                            className={`${isReleaseNumber ? 'px-1' : 'px-2'} py-0.5 text-center text-[10px] font-bold text-gray-900 uppercase tracking-wider bg-gray-100 border-r border-gray-300`}
                                                        >
                                                            {displayHeader}
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
                                                        {hasJobsData
                                                            ? 'No records match the selected filters.'
                                                            : 'No records found.'
                                                        }
                                                    </td>
                                                </tr>
                                            ) : (
                                                displayJobs.map((row, index) => (
                                                    <JobsTableRow
                                                        key={row.id}
                                                        row={row}
                                                        columns={columnHeaders}
                                                        formatCellValue={(value, columnName) => formatCellValue(value, columnName)}
                                                        formatDate={formatDate}
                                                        rowIndex={index}
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

            {/* Release Modal */}
            {showReleaseModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl shadow-2xl max-w-3xl w-full mx-4 max-h-[90vh] flex flex-col">
                        <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                            <div className="flex items-center justify-between">
                                <h2 className="text-2xl font-bold text-white">Release Job Data</h2>
                                <button
                                    onClick={handleCloseModal}
                                    className="text-white hover:text-gray-200 text-2xl font-bold"
                                    disabled={releasing}
                                >
                                    ×
                                </button>
                            </div>
                        </div>

                        <div className="p-6 flex-1 overflow-y-auto">
                            <div className="mb-4">
                                <label className="block text-sm font-semibold text-gray-700 mb-2">
                                    Paste Data (CSV or tab-separated from Google Sheets)
                                </label>
                                <p className="text-xs text-gray-600 mb-2">
                                    Expected columns: Job #, Release #, Job, Description, Fab Hrs, Install HRS, Paint color, PM, BY, Released, Fab Order
                                </p>
                                <textarea
                                    value={csvData}
                                    onChange={handleCsvDataChange}
                                    placeholder="Paste data here (supports CSV or tab-separated from Google Sheets)..."
                                    className="w-full h-64 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500 font-mono text-sm"
                                    disabled={releasing}
                                />
                            </div>

                            {/* Preview Table */}
                            {parsedPreview && parsedPreview.length > 0 && (
                                <div className="mb-4">
                                    <h3 className="text-sm font-semibold text-gray-700 mb-2">
                                        Preview ({parsedPreview.length} row{parsedPreview.length !== 1 ? 's' : ''})
                                    </h3>
                                    <div className="border border-gray-300 rounded-lg overflow-hidden">
                                        <div className="overflow-x-auto max-h-96">
                                            <table className="w-full text-xs border-collapse">
                                                <thead className="bg-gray-100 sticky top-0">
                                                    <tr>
                                                        {['Job #', 'Release #', 'Job', 'Description', 'Fab Hrs', 'Install HRS', 'Paint color', 'PM', 'BY', 'Released', 'Fab Order'].map((col) => (
                                                            <th
                                                                key={col}
                                                                className="px-2 py-1.5 text-left font-semibold text-gray-700 border-b border-gray-300 whitespace-nowrap"
                                                            >
                                                                {col}
                                                            </th>
                                                        ))}
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {parsedPreview.map((row, idx) => (
                                                        <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                                                            {['Job #', 'Release #', 'Job', 'Description', 'Fab Hrs', 'Install HRS', 'Paint color', 'PM', 'BY', 'Released', 'Fab Order'].map((col) => (
                                                                <td
                                                                    key={col}
                                                                    className="px-2 py-1.5 border-b border-gray-200 text-gray-900 whitespace-nowrap"
                                                                >
                                                                    {row[col] || <span className="text-gray-400">—</span>}
                                                                </td>
                                                            ))}
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {releaseError && (
                                <div className="mb-4 bg-red-50 border-l-4 border-red-500 text-red-700 px-4 py-3 rounded">
                                    <p className="font-semibold">Error</p>
                                    <p className="text-sm">{releaseError}</p>
                                </div>
                            )}

                            {releaseSuccess && (
                                <div className="mb-4 bg-green-50 border-l-4 border-green-500 text-green-700 px-4 py-3 rounded">
                                    <p className="font-semibold">Success!</p>
                                    <p className="text-sm">
                                        Processed: {releaseSuccess.processed} |
                                        Created: {releaseSuccess.created} |
                                        Updated: {releaseSuccess.updated}
                                        {releaseSuccess.trello_cards_created > 0 && ` | Trello Cards Created: ${releaseSuccess.trello_cards_created}`}
                                        {releaseSuccess.errors > 0 && ` | Errors: ${releaseSuccess.errors}`}
                                    </p>
                                    {releaseSuccess.trello_errors && releaseSuccess.trello_errors.length > 0 && (
                                        <div className="mt-2 text-xs">
                                            <p className="font-semibold">Trello Errors:</p>
                                            <ul className="list-disc list-inside">
                                                {releaseSuccess.trello_errors.map((err, idx) => (
                                                    <li key={idx}>
                                                        Job {err.job}-{err.release}: {err.error}
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>

                        <div className="px-6 py-4 bg-gray-50 rounded-b-xl flex justify-end gap-3">
                            <button
                                onClick={handleCloseModal}
                                className="px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg font-medium hover:bg-gray-50 transition-all"
                                disabled={releasing}
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleReleaseSubmit}
                                disabled={releasing || !csvData.trim()}
                                className={`px-4 py-2 rounded-lg font-medium transition-all ${releasing || !csvData.trim()
                                    ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                    : 'bg-accent-500 text-white hover:bg-accent-600'
                                    }`}
                            >
                                {releasing ? (
                                    <>
                                        <span className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></span>
                                        Releasing...
                                    </>
                                ) : (
                                    'Release'
                                )}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default JobLog;

