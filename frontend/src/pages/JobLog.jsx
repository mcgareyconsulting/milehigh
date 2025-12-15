import React, { useMemo, useEffect, useRef, useState } from 'react';
import { useJobsDataFetching } from '../hooks/useJobsDataFetching';
import { useJobsFilters } from '../hooks/useJobsFilters';
import { JobsTableRow } from '../components/JobsTableRow';

function JobLog() {
    const filterSectionRef = useRef(null);
    const [filterSectionHeight, setFilterSectionHeight] = useState(140);
    const { jobs, columns, loading, error: fetchError, lastUpdated, refetch } = useJobsDataFetching();

    // Use the filters hook
    const {
        selectedProjectName,
        selectedStages,
        jobNumberSearch,
        releaseNumberSearch,
        sortBy,
        showNotComplete,
        showNotShippingComplete,
        showBeforePaintComplete,
        setSelectedProjectName,
        setSelectedStages,
        setJobNumberSearch,
        setReleaseNumberSearch,
        setSortBy,
        setShowNotComplete,
        setShowNotShippingComplete,
        setShowBeforePaintComplete,
        projectNameOptions,
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

    // Measure filter section height
    useEffect(() => {
        const updateHeight = () => {
            if (filterSectionRef.current) {
                setFilterSectionHeight(filterSectionRef.current.offsetHeight);
            }
        };
        updateHeight();
        window.addEventListener('resize', updateHeight);
        return () => window.removeEventListener('resize', updateHeight);
    }, [selectedProjectName, selectedStages, projectNameOptions]);

    return (
        <div className="w-full min-h-screen bg-white" style={{ width: '100%', minWidth: '100%' }}>
            <div className="w-full" style={{ width: '100%' }}>
                <div ref={filterSectionRef} className="sticky top-0 bg-white z-10 border-b border-gray-300">
                    <div className="p-2">
                        <div className="flex flex-col gap-3">
                            <div>
                                <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                    Project Name
                                </label>
                                <div className="grid gap-0.5" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(80px, 1fr))` }}>
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
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                        Stage
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
                                <div>
                                    <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                        Filters
                                    </label>
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <button
                                            onClick={() => setSortBy(sortBy === 'fab_order_asc' ? 'default' : 'fab_order_asc')}
                                            className={`px-3 py-1.5 rounded text-xs font-medium shadow-sm transition-all ${sortBy === 'fab_order_asc'
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
                                                // When activating, also sort by fab order ascending
                                                if (newValue) {
                                                    setSortBy('fab_order_asc');
                                                }
                                            }}
                                            className={`px-3 py-1.5 rounded text-xs font-medium shadow-sm transition-all ${showNotComplete
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
                                                // When activating, also sort by fab order ascending
                                                if (newValue) {
                                                    setSortBy('fab_order_asc');
                                                }
                                            }}
                                            className={`px-3 py-1.5 rounded text-xs font-medium shadow-sm transition-all ${showNotShippingComplete
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
                                                // When activating, also sort by fab order ascending
                                                if (newValue) {
                                                    setSortBy('fab_order_asc');
                                                }
                                            }}
                                            className={`px-3 py-1.5 rounded text-xs font-medium shadow-sm transition-all ${showBeforePaintComplete
                                                ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                }`}
                                        >
                                            Before Paint Complete
                                        </button>
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
                                <div className="px-2 py-1 bg-white border border-gray-200 text-gray-600 rounded text-xs font-medium shadow-sm">
                                    Total: <span className="text-gray-900">{displayJobs.length}</span> records
                                </div>
                                <div className="text-xs text-gray-500 ml-auto">
                                    Last updated: <span className="font-medium text-gray-700">{formattedLastUpdated}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="p-2">
                    {loading && (
                        <div className="text-center py-8">
                            <p className="text-gray-600">Loading Jobs data...</p>
                        </div>
                    )}

                    {fetchError && !loading && (
                        <div className="bg-red-50 border border-red-500 text-red-700 px-4 py-2">
                            <p className="font-semibold">Unable to load Jobs data</p>
                            <p className="text-sm mt-1">{fetchError}</p>
                        </div>
                    )}

                    {!loading && !fetchError && (
                        <div className="overflow-x-auto overflow-y-auto" style={{ maxHeight: `calc(100vh - ${filterSectionHeight}px - 20px)` }}>
                            <table className="w-full border border-gray-300" style={{ borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr>
                                        {columnHeaders.map((column, index) => {
                                            const isReleaseNumber = column === 'Release #';
                                            const displayHeader = column === 'Release #' ? 'rel. #' : column;
                                            return (
                                                <th
                                                    key={column}
                                                    className={`${isReleaseNumber ? 'px-1' : 'px-2'} py-2.5 text-center text-[10px] font-bold text-gray-900 uppercase`}
                                                    style={{
                                                        position: 'sticky',
                                                        top: 0,
                                                        zIndex: 20,
                                                        backgroundColor: '#e5e7eb',
                                                        borderTop: '2px solid #6b7280',
                                                        borderBottom: '3px solid #6b7280',
                                                        borderLeft: index === 0 ? '1px solid #6b7280' : '1px solid #d1d5db',
                                                        borderRight: '1px solid #d1d5db',
                                                        boxShadow: '0 2px 4px -1px rgba(0, 0, 0, 0.1)'
                                                    }}
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
                                                className="px-6 py-12 text-center text-gray-500 font-medium bg-white"
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
                    )}
                </div>
            </div>
        </div>
    );
}

export default JobLog;

