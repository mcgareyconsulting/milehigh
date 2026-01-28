import React, { useMemo, useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useJobsDataFetching } from '../hooks/useJobsDataFetching';
import { useJobsFilters } from '../hooks/useJobsFilters';
import { useJobsDragAndDrop } from '../hooks/useJobsDragAndDrop';
import { JobsTableRow } from '../components/JobsTableRow';
import { jobsApi } from '../services/jobsApi';

function JobLog() {
    const navigate = useNavigate();
    const { jobs, columns, loading, error: fetchError, lastUpdated, refetch, fetchAll } = useJobsDataFetching();
    const [showReleaseModal, setShowReleaseModal] = useState(false);
    const [csvData, setCsvData] = useState('');
    const [parsedPreview, setParsedPreview] = useState(null);
    const [releasing, setReleasing] = useState(false);
    const [releaseError, setReleaseError] = useState(null);
    const [releaseSuccess, setReleaseSuccess] = useState(null);
    const [recalculating, setRecalculating] = useState(false);
    const [recalculateError, setRecalculateError] = useState(null);
    const [recalculateSuccess, setRecalculateSuccess] = useState(null);

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
        stageOptions,
        stageColors,
        displayJobs,
        resetFilters,
        toggleStage,
        selectedSubset,
        setSelectedSubset,
        ALL_OPTION_VALUE,
    } = useJobsFilters(jobs);

    // Update fab order handler (refetch after update to show collision detection changes)
    const updateFabOrder = useCallback(async (job, release, fabOrder) => {
        try {
            await jobsApi.updateFabOrder(job, release, fabOrder);
            // Refetch immediately to show collision detection changes and latest state
            await refetch(true);
        } catch (error) {
            // Error is already handled in the component, just rethrow
            throw error;
        }
    }, [refetch]);

    // Drag and drop functionality (disabled for now)
    // const {
    //     draggedIndex,
    //     dragOverIndex,
    //     handleDragStart,
    //     handleDragOver,
    //     handleDragLeave,
    //     handleDrop,
    // } = useJobsDragAndDrop(jobs, displayJobs, updateFabOrder, selectedSubset);

    // Disabled drag and drop - set to null/empty handlers
    const draggedIndex = null;
    const dragOverIndex = null;
    const handleDragStart = () => { };
    const handleDragOver = () => { };
    const handleDragLeave = () => { };
    const handleDrop = () => { };

    const formatDate = (dateValue) => {
        if (!dateValue) return '—';
        try {
            // Handle ISO date strings (YYYY-MM-DD) - parse directly to avoid timezone issues
            if (typeof dateValue === 'string' && /^\d{4}-\d{2}-\d{2}/.test(dateValue)) {
                // Extract date parts directly from ISO string to avoid timezone conversion
                const parts = dateValue.split('T')[0].split('-');
                if (parts.length === 3) {
                    const year = parts[0];
                    const month = parts[1];
                    const day = parts[2];
                    // Return in MM/DD/YY format
                    return `${month}/${day}/${year.slice(-2)}`;
                }
            }
            // Fallback to Date object parsing for other formats
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

    const handleRecalculateScheduling = async () => {
        if (!window.confirm('Recalculate scheduling for all jobs? This will update start_install and comp_eta fields.')) {
            return;
        }

        setRecalculating(true);
        setRecalculateError(null);
        setRecalculateSuccess(null);

        try {
            const result = await jobsApi.recalculateScheduling();
            setRecalculateSuccess({
                total_jobs: result.total_jobs || 0,
                updated: result.updated || 0,
                errors: result.errors || []
            });

            // Refresh the job data
            await fetchAll();

            // Clear success message after 5 seconds
            setTimeout(() => {
                setRecalculateSuccess(null);
            }, 5000);
        } catch (error) {
            setRecalculateError(error.message || 'Failed to recalculate scheduling');
            setTimeout(() => {
                setRecalculateError(null);
            }, 5000);
        } finally {
            setRecalculating(false);
        }
    };

    const handlePrint = () => {
        // First, sort all jobs by Job # first, then PM
        const sortedJobs = [...displayJobs].sort((a, b) => {
            // First sort by Job #
            const jobA = a['Job #'] || 0;
            const jobB = b['Job #'] || 0;
            if (jobA !== jobB) {
                return jobA - jobB;
            }
            // Then sort by PM (treat null/empty as empty string for sorting)
            const pmA = (a['PM'] || '').toString().toLowerCase();
            const pmB = (b['PM'] || '').toString().toLowerCase();
            return pmA.localeCompare(pmB);
        });

        // Group jobs by PM, maintaining the sorted order within each PM group
        const jobsByPM = {};
        sortedJobs.forEach(job => {
            const pm = job['PM'] || 'No PM';
            if (!jobsByPM[pm]) {
                jobsByPM[pm] = [];
            }
            jobsByPM[pm].push(job);
        });

        // Sort each PM group by Job # to ensure proper ordering
        Object.keys(jobsByPM).forEach(pm => {
            jobsByPM[pm].sort((a, b) => {
                const jobA = a['Job #'] || 0;
                const jobB = b['Job #'] || 0;
                return jobA - jobB;
            });
        });

        // Create printable HTML
        let printHTML = `
<!DOCTYPE html>
<html>
<head>
    <title>Job Log - Print</title>
    <style>
        @media print {
            @page {
                /* 11x17 tabloid in landscape orientation */
                size: 11in 17in landscape;
                margin: 0.5in;
            }
            .pm-group {
                page-break-after: always;
            }
            .pm-group:last-child {
                page-break-after: auto;
            }
        }
        body {
            font-family: Arial, sans-serif;
            font-size: 10px;
            margin: 0;
            padding: 20px;
        }
        h1 {
            font-size: 18px;
            margin-bottom: 10px;
            color: #333;
        }
        .pm-header {
            font-size: 14px;
            font-weight: bold;
            margin: 20px 0 10px 0;
            padding: 8px;
            background-color: #f0f0f0;
            border-bottom: 2px solid #333;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }
        th {
            background-color: #e0e0e0;
            border: 1px solid #999;
            padding: 6px 4px;
            text-align: center;
            font-weight: bold;
            font-size: 9px;
            white-space: nowrap;
        }
        td {
            border: 1px solid #ccc;
            padding: 4px;
            text-align: center;
            font-size: 9px;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .no-data {
            text-align: center;
            padding: 20px;
            color: #666;
        }
    </style>
</head>
<body>
    <h1>Job Log - Printed ${new Date().toLocaleString()}</h1>
`;

        // Generate table for each PM group
        Object.keys(jobsByPM).sort().forEach((pm, pmIndex, pmArray) => {
            const pmJobs = jobsByPM[pm];
            const isLastPM = pmIndex === pmArray.length - 1;

            printHTML += `
    <div class="pm-group"${isLastPM ? '' : ' style="page-break-after: always;"'}>
        <div class="pm-header">PM: ${pm}</div>
        <table>
            <thead>
                <tr>
                    ${columnHeaders.map(col => {
                const displayHeader = col === 'Release #' ? 'rel. #' : col;
                return `<th>${displayHeader}</th>`;
            }).join('')}
                </tr>
            </thead>
            <tbody>
`;

            pmJobs.forEach(job => {
                printHTML += '<tr>';
                columnHeaders.forEach(column => {
                    let value = job[column];

                    // Format date columns
                    if (column === 'Released' || column === 'Start install' || column === 'Comp. ETA') {
                        value = formatDate(value);
                    } else {
                        value = formatCellValue(value, column);
                    }

                    // Escape HTML
                    const displayValue = String(value || '—').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    printHTML += `<td>${displayValue}</td>`;
                });
                printHTML += '</tr>';
            });

            printHTML += `
            </tbody>
        </table>
    </div>
`;
        });

        printHTML += `
</body>
</html>
`;

        // Open print window
        const printWindow = window.open('', '_blank');
        printWindow.document.write(printHTML);
        printWindow.document.close();

        // Wait for content to load, then trigger print
        printWindow.onload = () => {
            setTimeout(() => {
                printWindow.print();
            }, 250);
        };
    };

    return (
        <div className="w-full h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-2 px-2 flex flex-col" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-full mx-auto w-full h-full flex flex-col" style={{ width: '100%' }}>
                <div className="bg-white rounded-2xl shadow-xl overflow-hidden flex flex-col h-full">
                    <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-4 py-3 flex-shrink-0">
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
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={handlePrint}
                                    disabled={!hasData || loading}
                                    className={`px-4 py-2 rounded-lg font-medium shadow-sm transition-all flex items-center gap-2 ${!hasData || loading
                                        ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                        : 'bg-white text-accent-600 hover:bg-accent-50'
                                        }`}
                                >
                                    🖨️ Print
                                </button>
                                <button
                                    onClick={() => navigate('/pm-board')}
                                    className="px-4 py-2 bg-white text-accent-600 rounded-lg font-medium shadow-sm hover:bg-accent-50 transition-all flex items-center gap-2"
                                >
                                    📋 PM Board
                                </button>
                                <button
                                    onClick={handleReleaseClick}
                                    className="px-4 py-2 bg-white text-accent-600 rounded-lg font-medium shadow-sm hover:bg-accent-50 transition-all flex items-center gap-2"
                                >
                                    📋 Release
                                </button>
                                <button
                                    onClick={handleRecalculateScheduling}
                                    disabled={recalculating}
                                    className={`px-4 py-2 rounded-lg font-medium shadow-sm transition-all flex items-center gap-2 ${recalculating
                                        ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                        : 'bg-white text-accent-600 hover:bg-accent-50'
                                        }`}
                                >
                                    {recalculating ? (
                                        <>
                                            <span className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-accent-600"></span>
                                            Calculating...
                                        </>
                                    ) : (
                                        <>
                                            ⏱️ Refresh Schedule
                                        </>
                                    )}
                                </button>
                            </div>
                        </div>
                    </div>

                    {/* Success/Error Messages */}
                    {recalculateSuccess && (
                        <div className="mx-2 mb-2 p-3 bg-green-50 border border-green-200 rounded-lg">
                            <p className="text-green-800 text-sm">
                                ✓ Scheduling updated: {recalculateSuccess.updated} of {recalculateSuccess.total_jobs} jobs updated
                                {recalculateSuccess.errors && recalculateSuccess.errors.length > 0 && (
                                    <span className="text-orange-600"> ({recalculateSuccess.errors.length} errors)</span>
                                )}
                            </p>
                        </div>
                    )}
                    {recalculateError && (
                        <div className="mx-2 mb-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                            <p className="text-red-800 text-sm">✗ {recalculateError}</p>
                        </div>
                    )}

                    <div className="p-2 flex flex-col flex-1 min-h-0 space-y-1.5">
                        <div className="bg-gray-100 rounded-lg p-1.5 border border-gray-200 flex-shrink-0">
                            <div className="grid grid-cols-2 gap-x-1.5 gap-y-1">
                                {/* Top Left: Project Name */}
                                <div>
                                    <label className="block text-sm font-bold text-gray-800 mb-1">
                                        Project Name
                                    </label>
                                    <div className="grid grid-cols-8 gap-1">
                                        <button
                                            onClick={() => setSelectedProjectName(ALL_OPTION_VALUE)}
                                            className={`px-0.5 py-0.5 rounded text-[9px] font-medium transition-all truncate ${selectedProjectName === ALL_OPTION_VALUE
                                                ? 'bg-blue-700 text-white'
                                                : 'bg-white border border-gray-400 text-gray-700 hover:bg-gray-50'
                                                }`}
                                            title="All"
                                        >
                                            All
                                        </button>
                                        {projectNameOptions.map((option) => {
                                            const truncated = option.length > 15 ? option.substring(0, 15) : option;
                                            return (
                                                <button
                                                    key={option}
                                                    onClick={() => setSelectedProjectName(option)}
                                                    className={`px-0.5 py-0.5 rounded text-[9px] font-medium transition-all truncate ${selectedProjectName === option
                                                        ? 'bg-blue-700 text-white'
                                                        : 'bg-white border border-gray-400 text-gray-700 hover:bg-gray-50'
                                                        }`}
                                                    title={option}
                                                >
                                                    {truncated}
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>

                                {/* Top Right: Filters */}
                                <div>
                                    <label className="block text-sm font-bold text-gray-800 mb-1">
                                        Filters
                                    </label>
                                    <div className="flex flex-wrap gap-1.5">
                                        <button
                                            onClick={() => setSelectedSubset(selectedSubset === 'job_order' ? null : 'job_order')}
                                            className={`px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap ${selectedSubset === 'job_order'
                                                ? 'bg-blue-700 text-white'
                                                : 'bg-white border border-gray-400 text-gray-700 hover:bg-gray-50'
                                                }`}
                                        >
                                            Job Order
                                        </button>
                                        <button
                                            onClick={() => setSelectedSubset(selectedSubset === 'ready_to_ship' ? null : 'ready_to_ship')}
                                            className={`px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap ${selectedSubset === 'ready_to_ship'
                                                ? 'bg-blue-700 text-white'
                                                : 'bg-white border border-gray-400 text-gray-700 hover:bg-gray-50'
                                                }`}
                                        >
                                            Ready to Ship
                                        </button>
                                        <button
                                            onClick={() => setSelectedSubset(selectedSubset === 'fab' ? null : 'fab')}
                                            className={`px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap ${selectedSubset === 'fab'
                                                ? 'bg-blue-700 text-white'
                                                : 'bg-white border border-gray-400 text-gray-700 hover:bg-gray-50'
                                                }`}
                                        >
                                            Fab
                                        </button>
                                    </div>
                                </div>

                                {/* Bottom Left: Reset Filters, Job #, Release #, Total */}
                                <div className="flex items-center gap-1.5 flex-wrap">
                                    <button
                                        onClick={resetFilters}
                                        className="px-2 py-0.5 bg-white border border-gray-400 text-gray-700 rounded text-xs font-semibold hover:bg-gray-50 transition-all whitespace-nowrap"
                                    >
                                        Reset Filters
                                    </button>
                                    <div className="flex items-center gap-1.5">
                                        <label className="text-xs font-semibold text-gray-700 whitespace-nowrap">
                                            Job #:
                                        </label>
                                        <input
                                            type="text"
                                            value={jobNumberSearch}
                                            onChange={(e) => setJobNumberSearch(e.target.value)}
                                            placeholder="Job #..."
                                            className="w-28 px-2 py-0.5 text-xs border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900"
                                        />
                                    </div>
                                    <div className="flex items-center gap-1.5">
                                        <label className="text-xs font-semibold text-gray-700 whitespace-nowrap">
                                            Release #:
                                        </label>
                                        <input
                                            type="text"
                                            value={releaseNumberSearch}
                                            onChange={(e) => setReleaseNumberSearch(e.target.value)}
                                            placeholder="Release #..."
                                            className="w-28 px-2 py-0.5 text-xs border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white text-gray-900"
                                        />
                                    </div>
                                    <div className="px-2 py-0.5 bg-white border border-gray-300 text-gray-700 rounded text-xs font-semibold">
                                        Total: <span className="text-gray-900 font-bold">{displayJobs.length}</span> records
                                    </div>
                                </div>

                                {/* Bottom Right: Last updated */}
                                <div className="flex items-center justify-end">
                                    <div className="text-xs text-gray-600 whitespace-nowrap">
                                        Last updated: <span className="font-semibold text-gray-800">{formattedLastUpdated}</span>
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
                            <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden flex-1 min-h-0 flex flex-col">
                                <div className="overflow-auto flex-1">
                                    <table className="w-full" style={{ borderCollapse: 'collapse' }}>
                                        <thead className="sticky top-0 z-10">
                                            <tr>
                                                {columnHeaders.map((column) => {
                                                    const isReleaseNumber = column === 'Release #';
                                                    // Display "rel. #" for Release # column header
                                                    const displayHeader = column === 'Release #' ? 'rel. #' : column;
                                                    return (
                                                        <th
                                                            key={column}
                                                            className={`${isReleaseNumber ? 'px-1' : 'px-2'} py-0.5 text-center text-[10px] font-bold text-gray-900 uppercase tracking-wider bg-gray-100 border-r border-gray-300 shadow-sm`}
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
                                                        onDragStart={handleDragStart}
                                                        onDragOver={handleDragOver}
                                                        onDragLeave={handleDragLeave}
                                                        onDrop={handleDrop}
                                                        isDragging={draggedIndex}
                                                        dragOverIndex={dragOverIndex}
                                                        onUpdate={() => refetch(true)}
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

