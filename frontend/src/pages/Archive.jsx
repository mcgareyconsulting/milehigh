/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Displays archived job releases in a filterable, read-only table so users can review completed work and optionally un-archive entries.
 * exports:
 *   Archive: Page component rendering the archived-jobs table with project filters and search
 * imports_from: [react, react-router-dom, ../hooks/useArchiveDataFetching, ../hooks/useJobsFilters, ../components/JobsTableRow, ../services/jobsApi, ../utils/auth]
 * imported_by: [App.jsx]
 * invariants:
 *   - Un-archive action is only available to admin users
 *   - Filter minimized state persists in localStorage under key 'ar_minimized'
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import React, { useMemo, useCallback, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useArchiveDataFetching } from '../hooks/useArchiveDataFetching';
import { useJobsFilters } from '../hooks/useJobsFilters';
import { JobsTableRow } from '../components/JobsTableRow';
import { jobsApi } from '../services/jobsApi';
import { checkAuth } from '../utils/auth';

function Archive() {
    const navigate = useNavigate();
    const { jobs, columns, loading, error: fetchError, refetch } = useArchiveDataFetching();

    const [isAdmin, setIsAdmin] = useState(false);
    const [isFilterMinimized, setIsFilterMinimized] = useState(
        () => localStorage.getItem('ar_minimized') === 'true'
    );

    useEffect(() => {
        const fetchUserInfo = async () => {
            try {
                const user = await checkAuth();
                setIsAdmin(user?.is_admin || false);
            } catch {
                setIsAdmin(false);
            }
        };
        fetchUserInfo();
    }, []);

    useEffect(() => {
        localStorage.setItem('ar_minimized', isFilterMinimized);
    }, [isFilterMinimized]);

    // Use the filters hook
    const {
        selectedProjectNames,
        search,
        setSelectedProjectNames,
        setSearch,
        projectNameOptions,
        stageToGroup,
        stageGroupColors,
        displayJobs,
        totalFabHrs,
        totalInstallHrs,
        resetFilters,
    } = useJobsFilters(jobs);

    const formatDate = (dateValue) => {
        if (!dateValue) return '—';
        try {
            if (typeof dateValue === 'string' && /^\d{4}-\d{2}-\d{2}/.test(dateValue)) {
                const parts = dateValue.split('T')[0].split('-');
                if (parts.length === 3) {
                    const year = parts[0];
                    const month = parts[1];
                    const day = parts[2];
                    return `${month}/${day}/${year.slice(-2)}`;
                }
            }
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
        if (columnName === 'Fab Hrs' || columnName === 'Install HRS') {
            const numValue = parseFloat(value);
            if (!isNaN(numValue)) {
                return numValue.toFixed(2);
            }
        }
        return value;
    };

    const handleUnarchiveJob = async (row) => {
        await jobsApi.unarchiveRelease(row['Job #'], row['Release #']);
        refetch();
    };

    const hasData = displayJobs.length > 0;
    const hasJobsData = !loading && jobs.length > 0;

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

    const columnHeaders = useMemo(() => {
        return columnOrder.filter(col => columns.includes(col) || col === 'Urgency');
    }, [columns]);

    const tableColumnCount = columnHeaders.length;

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
        <div className="w-full h-[calc(100vh-3.5rem)] bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 py-2 px-2 flex flex-col" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-full mx-auto w-full h-full flex flex-col" style={{ width: '100%' }}>
                <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl overflow-hidden flex flex-col h-full">

                    <div className="p-2 flex flex-col flex-1 min-h-0 space-y-1.5">
                        <div className="bg-gray-100 dark:bg-slate-700 rounded-lg p-1.5 border border-gray-200 dark:border-slate-600 flex-shrink-0 space-y-1.5">

                            {/* Minimized project pills — show selected projects when collapsed */}
                            {isFilterMinimized && selectedProjectNames.length > 0 && (
                                <div className="flex items-center gap-1 flex-wrap text-xs">
                                    <span className="font-semibold text-gray-500 dark:text-slate-400">Projects:</span>
                                    {selectedProjectNames.map(name => (
                                        <span key={name} className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 rounded-full font-medium">
                                            {name}
                                        </span>
                                    ))}
                                </div>
                            )}

                            {/* Row 1: Project name buttons — only visible when expanded */}
                            {!isFilterMinimized && (
                                <div className="grid gap-1" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))' }}>
                                    <button
                                        onClick={() => setSelectedProjectNames([])}
                                        className={`w-full px-2.5 py-1 rounded text-xs font-medium transition-all ${selectedProjectNames.length === 0
                                            ? 'bg-blue-700 text-white'
                                            : 'bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-200 dark:hover:bg-slate-500'
                                            }`}
                                    >
                                        All
                                    </button>
                                    {projectNameOptions.map((option) => (
                                        <button
                                            key={option}
                                            onClick={() => {
                                                setSelectedProjectNames(prev =>
                                                    prev.includes(option)
                                                        ? prev.filter(name => name !== option)
                                                        : [...prev, option]
                                                );
                                            }}
                                            className={`w-full px-2.5 py-1 rounded text-xs font-medium transition-all ${selectedProjectNames.includes(option)
                                                ? 'bg-blue-700 text-white'
                                                : 'bg-white dark:bg-slate-600 border border-gray-300 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-200 dark:hover:bg-slate-500'
                                                }`}
                                            title={option}
                                        >
                                            {option.length > 20 ? option.slice(0, 20) + '…' : option}
                                        </button>
                                    ))}
                                </div>
                            )}

                            {/* Row 2: Actions + chevron — always visible */}
                            <div className="flex items-center gap-1.5">
                                <div className="flex items-center gap-1.5">
                                    <button
                                        onClick={() => navigate('/job-log')}
                                        className="px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500"
                                    >
                                        📋 Job Log
                                    </button>
                                    <button
                                        onClick={() => refetch()}
                                        className="px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500"
                                    >
                                        ⟳ Refresh
                                    </button>
                                </div>
                                <div className="ml-auto">
                                    <button
                                        onClick={() => setIsFilterMinimized(!isFilterMinimized)}
                                        className="p-1.5 rounded-lg hover:bg-gray-300 dark:hover:bg-slate-600 transition-colors"
                                        title={isFilterMinimized ? "Expand projects" : "Collapse projects"}
                                    >
                                        <span className="text-xl leading-none text-gray-600 dark:text-slate-300">{isFilterMinimized ? '▾' : '▴'}</span>
                                    </button>
                                </div>
                            </div>

                            {/* Row 3: Reset + search + stats — always visible */}
                            <div className="flex items-center justify-between gap-1.5 flex-wrap">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                    <button
                                        onClick={resetFilters}
                                        className="text-sm text-blue-600 dark:text-blue-400 underline hover:no-underline whitespace-nowrap"
                                    >
                                        Reset Filters
                                    </button>
                                    <div className="flex items-center gap-1.5">
                                        <label className="text-xs font-semibold text-gray-700 dark:text-slate-200 whitespace-nowrap">
                                            Search:
                                        </label>
                                        <input
                                            type="text"
                                            value={search}
                                            onChange={(e) => setSearch(e.target.value)}
                                            placeholder="Job #, release, name, description..."
                                            className="w-64 px-2 py-0.5 text-xs border border-gray-300 dark:border-slate-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-slate-600 text-gray-900 dark:text-slate-100"
                                        />
                                    </div>
                                </div>
                                <div className="flex items-center gap-3 text-xs font-semibold text-gray-700 dark:text-slate-200">
                                    <span>
                                        Total: <span className="text-gray-900 dark:text-slate-100 font-bold">{displayJobs.length}</span> records
                                    </span>
                                    <span className="text-gray-300 dark:text-slate-500">|</span>
                                    <span>
                                        Fab HRS: <span className="text-gray-900 dark:text-slate-100 font-bold">{totalFabHrs.toFixed(2)}</span>
                                    </span>
                                    <span className="text-gray-300 dark:text-slate-500">|</span>
                                    <span>
                                        Install HRS: <span className="text-gray-900 dark:text-slate-100 font-bold">{totalInstallHrs.toFixed(2)}</span>
                                    </span>
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
                                                    const displayHeader = column === 'Release #' ? 'rel. #' : column === 'Job Comp' ? 'Install Prog' : column;
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
                                                {isAdmin && (
                                                    <th className="px-2 py-0.5 text-center text-xl font-bold text-gray-900 dark:text-slate-100 uppercase tracking-wider bg-gray-100 dark:bg-slate-700 border-r border-gray-300 dark:border-slate-600 shadow-sm w-12">
                                                        ⚙
                                                    </th>
                                                )}
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {!hasData ? (
                                                <tr>
                                                    <td
                                                        colSpan={tableColumnCount + (isAdmin ? 1 : 0)}
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
                                                        isAdmin={isAdmin}
                                                        onUnarchive={handleUnarchiveJob}
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

export default Archive;
