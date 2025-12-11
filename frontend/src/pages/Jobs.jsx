import React, { useMemo } from 'react';
import { useJobsDataFetching } from '../hooks/useJobsDataFetching';
import { JobsTableRow } from '../components/JobsTableRow';

function Jobs() {
    const { jobs, columns, loading, error: fetchError, lastUpdated, refetch } = useJobsDataFetching();

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

    const hasData = jobs.length > 0;

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
                            <div>
                                <h1 className="text-3xl font-bold text-white">Jobs</h1>
                            </div>
                        </div>
                    </div>

                    <div className="p-6 space-y-4">
                        <div className="bg-gradient-to-r from-gray-50 to-accent-50 rounded-xl p-4 border border-gray-200 shadow-sm">
                            <div className="flex items-center gap-2">
                                <div className="px-2 py-1 bg-white border border-gray-200 text-gray-600 rounded text-xs font-medium shadow-sm">
                                    Total: <span className="text-gray-900">{jobs.length}</span> records
                                </div>
                                <div className="text-xs text-gray-500 ml-auto">
                                    Last updated: <span className="font-medium text-gray-700">{formattedLastUpdated}</span>
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
                                                jobs.map((row, index) => (
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

