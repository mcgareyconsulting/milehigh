import React, { useMemo, useState, useCallback } from 'react';
import { useJobsDataFetching } from '../hooks/useJobsDataFetching';
import { JobsTableRow } from '../components/JobsTableRow';

const ALL_OPTION_VALUE = '__ALL__';

function Jobs() {
    const { jobs, columns, loading, error: fetchError, lastUpdated, refetch } = useJobsDataFetching();
    const [selectedProjectName, setSelectedProjectName] = useState(ALL_OPTION_VALUE);
    const [selectedStages, setSelectedStages] = useState([]); // Array of selected stage values
    const [jobNumberSearch, setJobNumberSearch] = useState('');
    const [releaseNumberSearch, setReleaseNumberSearch] = useState('');

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

    // Extract unique project name (Job) options from jobs
    const projectNameOptions = useMemo(() => {
        const values = new Set();
        jobs.forEach((job) => {
            const value = job['Job'];
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                values.add(String(value).trim());
            }
        });
        return Array.from(values).sort((a, b) => a.localeCompare(b));
    }, [jobs]);

    // Filter jobs by selected project name and search terms
    const displayJobs = useMemo(() => {
        let filtered = jobs;

        // Filter by project name
        if (selectedProjectName !== ALL_OPTION_VALUE) {
            filtered = filtered.filter((job) => {
                const jobName = job['Job'] ?? '';
                return String(jobName).trim() === selectedProjectName;
            });
        }

        // Filter by Job # (must match if provided)
        if (jobNumberSearch.trim() !== '') {
            const searchTerm = jobNumberSearch.trim();
            filtered = filtered.filter((job) => {
                const jobNumber = String(job['Job #'] ?? '').trim();
                return jobNumber.includes(searchTerm);
            });
        }

        // Filter by Release # (must match if provided)
        if (releaseNumberSearch.trim() !== '') {
            const searchTerm = releaseNumberSearch.trim();
            filtered = filtered.filter((job) => {
                const releaseNumber = String(job['Release #'] ?? '').trim();
                return releaseNumber.includes(searchTerm);
            });
        }

        // Filter by Stage (multiselect - must match any selected stage)
        // If "All" is selected (empty array), show all stages
        if (selectedStages.length > 0) {
            filtered = filtered.filter((job) => {
                const jobStage = job['Stage'] ?? '';
                return selectedStages.includes(String(jobStage).trim());
            });
        }

        return filtered;
    }, [jobs, selectedProjectName, jobNumberSearch, releaseNumberSearch, selectedStages]);

    const resetFilters = useCallback(() => {
        setSelectedProjectName(ALL_OPTION_VALUE);
        setSelectedStages([]);
        setJobNumberSearch('');
        setReleaseNumberSearch('');
    }, []);

    // Stage options for multiselect (using simplified labels)
    const stageOptions = [
        { value: 'Released', label: 'Released' },
        { value: 'Cut start', label: 'Cut start' },
        { value: 'Fit Up Complete.', label: 'Fitup comp' },
        { value: 'Paint complete', label: 'Paint comp' },
        { value: 'Store at MHMW for shipping', label: 'Store' },
        { value: 'Shipping planning', label: 'Ship plan' },
        { value: 'Shipping completed', label: 'Ship comp' }
    ];

    // Color mapping for each stage (matching dropdown colors)
    // Unselected: lighter background, selected: darker background with white text
    const stageColors = {
        'Released': {
            unselected: 'bg-blue-100 text-blue-800 border-blue-300',
            selected: 'bg-blue-600 text-white border-blue-700'
        },
        'Cut start': {
            unselected: 'bg-purple-100 text-purple-800 border-purple-300',
            selected: 'bg-purple-600 text-white border-purple-700'
        },
        'Fit Up Complete.': {
            unselected: 'bg-green-100 text-green-800 border-green-300',
            selected: 'bg-green-600 text-white border-green-700'
        },
        'Paint complete': {
            unselected: 'bg-yellow-100 text-yellow-800 border-yellow-300',
            selected: 'bg-yellow-600 text-white border-yellow-700'
        },
        'Store at MHMW for shipping': {
            unselected: 'bg-orange-100 text-orange-800 border-orange-300',
            selected: 'bg-orange-600 text-white border-orange-700'
        },
        'Shipping planning': {
            unselected: 'bg-indigo-100 text-indigo-800 border-indigo-300',
            selected: 'bg-indigo-600 text-white border-indigo-700'
        },
        'Shipping completed': {
            unselected: 'bg-gray-100 text-gray-800 border-gray-300',
            selected: 'bg-gray-600 text-white border-gray-700'
        }
    };

    const toggleStage = useCallback((stageValue) => {
        setSelectedStages(prev => {
            if (prev.includes(stageValue)) {
                return prev.filter(s => s !== stageValue);
            } else {
                return [...prev, stageValue];
            }
        });
    }, []);

    const hasData = displayJobs.length > 0;

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
                        </div>
                    </div>

                    <div className="p-6 space-y-4">
                        <div className="bg-gradient-to-r from-gray-50 to-accent-50 rounded-xl p-4 border border-gray-200 shadow-sm">
                            <div className="flex flex-col gap-3">
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                            📁 Project Name
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
                                    <div>
                                        <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                            🎯 Stage
                                        </label>
                                        <div className="grid grid-cols-8 gap-0.5">
                                            <button
                                                onClick={() => setSelectedStages([])}
                                                className={`px-0.5 py-0.5 rounded text-[9px] font-medium shadow-sm transition-all truncate ${selectedStages.length === 0
                                                    ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                    : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                    }`}
                                                title="All"
                                            >
                                                All
                                            </button>
                                            {stageOptions.map((option) => {
                                                const isSelected = selectedStages.includes(option.value);
                                                const colors = stageColors[option.value] || { unselected: 'bg-white border-gray-300 text-gray-700', selected: 'bg-gray-600 text-white border-gray-700' };
                                                const colorClass = isSelected ? colors.selected : colors.unselected;
                                                return (
                                                    <button
                                                        key={option.value}
                                                        onClick={() => toggleStage(option.value)}
                                                        className={`px-0.5 py-0.5 rounded text-[9px] font-medium shadow-sm transition-all truncate border ${colorClass}`}
                                                        title={option.value}
                                                    >
                                                        {option.label}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2 pt-2 flex-wrap">
                                    <button
                                        onClick={resetFilters}
                                        className="px-2 py-1 bg-white border border-accent-300 text-accent-700 rounded text-xs font-medium shadow-sm hover:bg-accent-50 transition-all"
                                    >
                                        Reset Filters
                                    </button>
                                    <div className="flex items-center gap-2">
                                        <label className="text-xs font-semibold text-gray-700 whitespace-nowrap">
                                            🔍 Job #:
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
                                            🔍 Release #:
                                        </label>
                                        <input
                                            type="text"
                                            value={releaseNumberSearch}
                                            onChange={(e) => setReleaseNumberSearch(e.target.value)}
                                            placeholder="Release #..."
                                            className="w-24 px-2 py-1 text-xs border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500 bg-white text-gray-900"
                                        />
                                    </div>
                                    <div className="px-2 py-1 bg-white border border-gray-200 text-gray-600 rounded text-xs font-medium shadow-sm">
                                        Total: <span className="text-gray-900">{displayJobs.length}</span> records
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
                                                        No records found.
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
        </div>
    );
}

export default Jobs;

