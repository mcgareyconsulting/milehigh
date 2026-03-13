import React, { useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useArchiveDataFetching } from '../hooks/useArchiveDataFetching';
import { useJobsFilters } from '../hooks/useJobsFilters';
import { JobsTableRow } from '../components/JobsTableRow';

function Archive() {
    const navigate = useNavigate();
    const { jobs, columns, loading, error: fetchError, refetch } = useArchiveDataFetching();

    // Use the filters hook
    const {
        selectedProjectNames,
        selectedStages,
        jobNumberSearch,
        releaseNumberSearch,
        setSelectedProjectNames,
        setSelectedStages,
        setJobNumberSearch,
        setReleaseNumberSearch,
        projectNameOptions,
        stageOptions,
        stageColors,
        stageToGroup,
        stageGroupColors,
        displayJobs,
        totalFabHrs,
        totalInstallHrs,
        resetFilters,
        toggleStage,
    } = useJobsFilters(jobs);

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

    // Check if we have data to display
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
        'Urgency',
        'Start install',
        'Comp. ETA',
        'Job Comp',
        'Invoiced',
        'Notes'
    ];

    const COLUMN_WIDTH_PERCENT = {
        'Job #': 3,
        'Release #': 3,
        'Job': 6,
        'Description': 9,
        'Fab Hrs': 5,
        'Install HRS': 5,
        'Paint color': 6,
        'PM': 3,
        'BY': 3,
        'Released': 5,
        'Fab Order': 6,
        'Stage': 9,
        'Urgency': 8,
        'Start install': 5,
        'Comp. ETA': 5,
        'Job Comp': 5,
        'Invoiced': 5,
        'Notes': 12,
    };

    // Filter and order columns based on defined order
    const columnHeaders = useMemo(() => {
        // Only include columns that exist in the data and are in our defined order
        return columnOrder.filter(col => columns.includes(col) || col === 'Urgency');
    }, [columns]);

    const tableColumnCount = columnHeaders.length;

    // Normalize column width percentages so visible columns sum to 100%
    const columnWidthPercents = useMemo(() => {
        const defaultWeight = 5;
        const total = columnHeaders.reduce((sum, col) => sum + (COLUMN_WIDTH_PERCENT[col] ?? defaultWeight), 0);
        return Object.fromEntries(
            columnHeaders.map((col) => {
                const weight = COLUMN_WIDTH_PERCENT[col] ?? defaultWeight;
                return [col, (weight / total) * 100];
            })
        );
    }, [columnHeaders]);

    return (
        <div className="h-full flex flex-col bg-[#f8fafc] dark:bg-slate-900">
            <div className="flex-1 overflow-hidden flex flex-col">
                <div className="flex-1 overflow-hidden flex flex-col">
                    <div className="bg-gradient-to-r from-accent-500 to-accent-600 text-white shadow-md">
                        <div className="px-6 py-6 flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <h1 className="text-3xl font-bold text-white">Archived Jobs</h1>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => navigate('/job-log')}
                                    className="px-4 py-2 bg-white dark:bg-slate-700 text-accent-600 dark:text-accent-300 rounded-lg font-medium shadow-sm hover:bg-accent-50 dark:hover:bg-slate-600 transition-all flex items-center gap-2"
                                >
                                    📋 Job Log
                                </button>
                            </div>
                        </div>
                    </div>

                    <div className="flex-1 overflow-hidden flex flex-col">
                        <div className="flex-1 flex flex-col m-4 gap-4">
                            {/* Filter Section */}
                            <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-xl shadow-sm">
                                <div className="p-4">
                                    <div className="mb-3">
                                        <h3 className="text-xs font-bold text-gray-700 dark:text-slate-200 uppercase tracking-wider mb-2">
                                            Stage Groups
                                        </h3>
                                        <div className="flex flex-wrap gap-1.5">
                                            {stageOptions.map((stage) => (
                                                <button
                                                    key={stage}
                                                    onClick={() => toggleStage(stage)}
                                                    className={`px-2 py-1 rounded text-xs font-semibold transition-all ${
                                                        selectedStages.includes(stage)
                                                            ? `bg-white dark:bg-slate-700 text-white shadow-md`
                                                            : 'bg-gray-200 dark:bg-slate-600 text-gray-700 dark:text-slate-300 opacity-60 hover:opacity-75'
                                                    }`}
                                                    style={selectedStages.includes(stage) ? { backgroundColor: stageColors[stage] } : undefined}
                                                >
                                                    {stage}
                                                </button>
                                            ))}
                                            <button
                                                onClick={resetFilters}
                                                className="ml-auto px-2 py-1 bg-gray-200 dark:bg-slate-600 text-gray-700 dark:text-slate-300 rounded text-xs font-semibold hover:bg-gray-300 dark:hover:bg-slate-500 transition-all"
                                            >
                                                Reset All
                                            </button>
                                        </div>
                                    </div>

                                    <div className="flex gap-2 flex-wrap">
                                        <div className="flex gap-2">
                                            <input
                                                type="text"
                                                value={jobNumberSearch}
                                                onChange={(e) => setJobNumberSearch(e.target.value)}
                                                placeholder="Job #..."
                                                className="w-24 px-2 py-0.5 text-xs border border-gray-300 dark:border-slate-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-slate-600 text-gray-900 dark:text-slate-100"
                                            />
                                            <input
                                                type="text"
                                                value={releaseNumberSearch}
                                                onChange={(e) => setReleaseNumberSearch(e.target.value)}
                                                placeholder="Release #..."
                                                className="w-28 px-2 py-0.5 text-xs border border-gray-300 dark:border-slate-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-slate-600 text-gray-900 dark:text-slate-100"
                                            />
                                        </div>
                                        <div className="px-2 py-0.5 bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 rounded text-xs font-semibold">
                                            Total: <span className="text-gray-900 dark:text-slate-100 font-bold">{displayJobs.length}</span> records
                                        </div>

                                        {/* Right side KPI chips */}
                                        <div className="flex items-center justify-end gap-2 ml-auto">
                                            <div className="px-2 py-0.5 bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 rounded text-xs font-semibold">
                                                Fab HRS: <span className="text-gray-900 dark:text-slate-100 font-bold">{totalFabHrs.toFixed(2)}</span>
                                            </div>
                                            <div className="px-2 py-0.5 bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 rounded text-xs font-semibold">
                                                Install HRS: <span className="text-gray-900 dark:text-slate-100 font-bold">{totalInstallHrs.toFixed(2)}</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {loading && (
                                <div className="text-center py-12">
                                    <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                                    <p className="text-gray-600 font-medium">Loading archived jobs...</p>
                                </div>
                            )}

                            {fetchError && !loading && (
                                <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-6 py-4 rounded-lg shadow-sm">
                                    <div className="flex items-start">
                                        <span className="text-xl mr-3">⚠️</span>
                                        <div>
                                            <p className="font-semibold">Unable to load archived jobs</p>
                                            <p className="text-sm mt-1">{fetchError}</p>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {!loading && !fetchError && (
                                <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-xl shadow-sm overflow-hidden flex-1 min-h-0 flex flex-col">
                                    <div className="job-log-table-scroll-hide-scrollbar overflow-auto flex-1">
                                        <table className="w-full" style={{ borderCollapse: 'collapse', tableLayout: 'fixed', width: '100%' }}>
                                            <thead className="sticky top-0 z-10">
                                                <tr>
                                                    {columnHeaders.map((column) => {
                                                        const isReleaseNumber = column === 'Release #';
                                                        const displayHeader = column === 'Release #' ? 'rel. #' : column;
                                                        const colWidthPct = columnWidthPercents[column];
                                                        return (
                                                            <th
                                                                key={column}
                                                                className={`${isReleaseNumber ? 'px-1' : 'px-2'} py-0.5 text-center text-[10px] font-bold text-gray-900 dark:text-slate-100 uppercase tracking-wider bg-gray-100 dark:bg-slate-700 border-r border-gray-300 dark:border-slate-600 shadow-sm`}
                                                                style={colWidthPct != null ? { width: `${colWidthPct}%` } : undefined}
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
                                                            className="px-6 py-12 text-center text-gray-500 dark:text-slate-400 font-medium bg-white dark:bg-slate-800 rounded-md"
                                                        >
                                                            {hasJobsData
                                                                ? 'No records match the selected filters.'
                                                                : 'No archived records found.'
                                                            }
                                                        </td>
                                                    </tr>
                                                ) : (
                                                    displayJobs.map((row, index) => (
                                                        <JobsTableRow
                                                            key={row.id}
                                                            row={row}
                                                            columns={columnHeaders}
                                                            isJumpToHighlight={false}
                                                            formatCellValue={(value, columnName) => formatCellValue(value, columnName)}
                                                            formatDate={formatDate}
                                                            rowIndex={index}
                                                            onDragStart={() => { }}
                                                            onDragOver={() => { }}
                                                            onDragLeave={() => { }}
                                                            onDrop={() => { }}
                                                            isDragging={null}
                                                            dragOverIndex={null}
                                                            onUpdate={() => refetch()}
                                                            stageToGroup={stageToGroup}
                                                            stageGroupColors={stageGroupColors}
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
        </div>
    );
}

export default Archive;
