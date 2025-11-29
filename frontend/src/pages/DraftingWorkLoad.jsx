import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import axios from 'axios';
import { useDataFetching } from '../hooks/useDataFetching';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const ALL_OPTION_VALUE = '__ALL__';

function DraftingWorkLoad() {
    const [selectedBallInCourt, setSelectedBallInCourt] = useState(ALL_OPTION_VALUE);
    const [selectedSubmittalManager, setSelectedSubmittalManager] = useState(ALL_OPTION_VALUE);
    const [selectedProjectName, setSelectedProjectName] = useState(ALL_OPTION_VALUE);
    const [projectNameSortMode, setProjectNameSortMode] = useState('normal'); // 'normal', 'a-z', 'z-a'
    const [uploading, setUploading] = useState(false);
    const [uploadError, setUploadError] = useState(null);
    const [uploadSuccess, setUploadSuccess] = useState(false);

    const { submittals, columns, loading, error, lastUpdated, refetch } = useDataFetching();
    const rows = submittals; // now that submittals is clean, we alias


    const matchesSelectedFilter = useCallback((row) => {
        // Check Ball In Court filter (handles comma-separated values for multiple assignees)
        if (selectedBallInCourt !== ALL_OPTION_VALUE) {
            const ballInCourtValue = (row.ball_in_court ?? '').toString().trim();
            // Check if selected value matches exactly OR appears in comma-separated list
            const ballInCourtNames = ballInCourtValue.split(',').map(name => name.trim());
            if (!ballInCourtNames.includes(selectedBallInCourt)) {
                return false;
            }
        }

        // Check Submittal Manager filter
        if (selectedSubmittalManager !== ALL_OPTION_VALUE) {
            const managerValue = row.submittal_manager ?? row['Submittal Manager'];
            if ((managerValue ?? '').toString().trim() !== selectedSubmittalManager) {
                return false;
            }
        }

        // Check Project Name filter
        if (selectedProjectName !== ALL_OPTION_VALUE) {
            const projectNameValue = row.project_name ?? row['Project Name'];
            if ((projectNameValue ?? '').toString().trim() !== selectedProjectName) {
                return false;
            }
        }

        return true;
    }, [selectedBallInCourt, selectedSubmittalManager, selectedProjectName]);

    const displayRows = useMemo(() => {
        const filtered = rows.filter(matchesSelectedFilter);

        // Sort based on Project Name sort mode
        if (projectNameSortMode === 'a-z') {
            return filtered.sort((a, b) => {
                const projectA = (a.project_name ?? a['Project Name'] ?? '').toString().trim();
                const projectB = (b.project_name ?? b['Project Name'] ?? '').toString().trim();
                if (projectA !== projectB) {
                    return projectA.localeCompare(projectB);
                }
                // Secondary sort: multi-assignee rows go to bottom within same project
                const ballA = (a.ball_in_court ?? '').toString();
                const ballB = (b.ball_in_court ?? '').toString();
                const hasMultipleA = ballA.includes(',');
                const hasMultipleB = ballB.includes(',');

                // Multi-assignee rows should go to the bottom
                if (hasMultipleA && !hasMultipleB) {
                    return 1; // A goes after B
                }
                if (!hasMultipleA && hasMultipleB) {
                    return -1; // A goes before B
                }

                // If both have multiple or both are single, sort by order_number or submittal_id
                if (hasMultipleA && hasMultipleB) {
                    return (a['Submittals Id'] || '').localeCompare(b['Submittals Id'] || '');
                }

                const orderA = a.order_number ?? a['Order Number'] ?? 999999;
                const orderB = b.order_number ?? b['Order Number'] ?? 999999;
                return orderA - orderB;
            });
        } else if (projectNameSortMode === 'z-a') {
            return filtered.sort((a, b) => {
                const projectA = (a.project_name ?? a['Project Name'] ?? '').toString().trim();
                const projectB = (b.project_name ?? b['Project Name'] ?? '').toString().trim();
                if (projectA !== projectB) {
                    return projectB.localeCompare(projectA);
                }
                // Secondary sort: multi-assignee rows go to bottom within same project
                const ballA = (a.ball_in_court ?? '').toString();
                const ballB = (b.ball_in_court ?? '').toString();
                const hasMultipleA = ballA.includes(',');
                const hasMultipleB = ballB.includes(',');

                // Multi-assignee rows should go to the bottom
                if (hasMultipleA && !hasMultipleB) {
                    return 1; // A goes after B
                }
                if (!hasMultipleA && hasMultipleB) {
                    return -1; // A goes before B
                }

                // If both have multiple or both are single, sort by order_number or submittal_id
                if (hasMultipleA && hasMultipleB) {
                    return (a['Submittals Id'] || '').localeCompare(b['Submittals Id'] || '');
                }

                const orderA = a.order_number ?? a['Order Number'] ?? 999999;
                const orderB = b.order_number ?? b['Order Number'] ?? 999999;
                return orderA - orderB;
            });
        } else {
            // Normal sort: by Ball In Court, then by order_number (as float)
            // Multi-assignee cases (comma-separated = reviewers) sort to the bottom
            return filtered.sort((a, b) => {
                const ballA = (a.ball_in_court ?? '').toString();
                const ballB = (b.ball_in_court ?? '').toString();

                // Check if either has multiple assignees (comma indicates reviewers)
                const hasMultipleA = ballA.includes(',');
                const hasMultipleB = ballB.includes(',');

                // Multi-assignee rows should go to the bottom
                // If one has multiple and the other doesn't, single assignee comes first
                if (hasMultipleA && !hasMultipleB) {
                    return 1; // A goes after B (A has multiple, B doesn't)
                }
                if (!hasMultipleA && hasMultipleB) {
                    return -1; // A goes before B (A doesn't have multiple, B does)
                }

                // If both have multiple assignees, sort them together alphabetically
                if (hasMultipleA && hasMultipleB) {
                    if (ballA !== ballB) {
                        return ballA.localeCompare(ballB);
                    }
                    // Tiebreaker: sort by submittal_id
                    return (a['Submittals Id'] || '').localeCompare(b['Submittals Id'] || '');
                }

                // Both are single assignees: sort alphabetically by ball_in_court
                if (ballA !== ballB) {
                    return ballA.localeCompare(ballB);
                }

                // Same ball_in_court: sort by order_number as float (nulls last)
                const orderA = a.order_number ?? a['Order Number'] ?? 999999;
                const orderB = b.order_number ?? b['Order Number'] ?? 999999;
                return orderA - orderB;
            });
        }
    }, [rows, matchesSelectedFilter, projectNameSortMode]);

    const ballInCourtOptions = useMemo(() => {
        const values = new Set();
        rows.forEach((row) => {
            const value = row.ball_in_court;
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                // Extract individual names from comma-separated values
                const names = String(value).split(',').map(name => name.trim()).filter(name => name !== '');
                names.forEach(name => values.add(name));
            }
        });
        return Array.from(values).sort((a, b) => a.localeCompare(b));
    }, [rows]);

    const submittalManagerOptions = useMemo(() => {
        const values = new Set();
        rows.forEach((row) => {
            const value = row.submittal_manager ?? row['Submittal Manager'];
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                values.add(String(value).trim());
            }
        });
        return Array.from(values).sort((a, b) => a.localeCompare(b));
    }, [rows]);

    const projectNameOptions = useMemo(() => {
        const values = new Set();
        rows.forEach((row) => {
            const value = row.project_name ?? row['Project Name'];
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                values.add(String(value).trim());
            }
        });
        return Array.from(values).sort((a, b) => a.localeCompare(b));
    }, [rows]);

    const formatDate = (dateValue) => {
        if (!dateValue) return '—';
        try {
            const date = new Date(dateValue);
            if (isNaN(date.getTime())) return '—';
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const year = date.getFullYear();
            return `${month}/${day}/${year}`;
        } catch (e) {
            return '—';
        }
    };

    const formatCellValue = (value) => {
        if (value === null || value === undefined || value === '') {
            return '—';
        }
        if (Array.isArray(value)) {
            return value.join(', ');
        }
        return value;
    };

    const resetFilters = () => {
        setSelectedBallInCourt(ALL_OPTION_VALUE);
        setSelectedSubmittalManager(ALL_OPTION_VALUE);
        setSelectedProjectName(ALL_OPTION_VALUE);
        setProjectNameSortMode('normal');
    };

    const handleProjectNameSortToggle = () => {
        if (projectNameSortMode === 'normal') {
            setProjectNameSortMode('a-z');
        } else if (projectNameSortMode === 'a-z') {
            setProjectNameSortMode('z-a');
        } else {
            setProjectNameSortMode('normal');
        }
    };

    const handleOrderNumberChange = async (submittalId, newValue) => {
        // Parse the value as float
        const parsedValue = newValue === '' || newValue === null || newValue === undefined
            ? null
            : parseFloat(newValue);

        // Validate it's a number if not null
        if (parsedValue !== null && isNaN(parsedValue)) {
            return; // Invalid input, don't update
        }

        try {
            await draftingWorkLoadApi.updateOrderNumber(submittalId, parsedValue);
            await refetch();
        } catch (err) {
            console.error(`Failed to update order for ${submittalId}:`, err);
            await refetch();
        }
    };

    const handleNotesChange = useCallback(async (submittalId, newValue) => {
        try {
            await axios.put(`${API_BASE_URL}/procore/api/drafting-work-load/notes`, {
                submittal_id: submittalId,
                notes: newValue
            });

            // Refresh data to get updated notes
            await refetch(true);
        } catch (err) {
            console.error(`Failed to update notes for ${submittalId}:`, err);
            // Refresh to get correct state
            await refetch(true);
        }
    }, [refetch]);

    const handleStatusChange = useCallback(async (submittalId, newValue) => {
        try {
            await axios.put(`${API_BASE_URL}/procore/api/drafting-work-load/submittal-drafting-status`, {
                submittal_id: submittalId,
                submittal_drafting_status: newValue
            });

            // Refresh data to get updated status
            await refetch(true);
        } catch (err) {
            console.error(`Failed to update status for ${submittalId}:`, err);
            // Refresh to get correct state
            await refetch(true);
        }
    }, [refetch]);


    const handleFileUpload = async (event) => {
        const file = event.target.files[0];
        if (!file) {
            return;
        }

        // Validate file type
        if (!file.name.toLowerCase().endsWith('.xlsx') && !file.name.toLowerCase().endsWith('.xls')) {
            setUploadError('Please select an Excel file (.xlsx or .xls)');
            setUploadSuccess(false);
            return;
        }

        setUploading(true);
        setUploadError(null);
        setUploadSuccess(false);

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await axios.post(
                `${API_BASE_URL}/procore/api/upload/drafting-workload-submittals`,
                formData,
                {
                    headers: {
                        'Content-Type': 'multipart/form-data',
                    },
                }
            );

            if (response.data.success) {
                setUploadSuccess(true);
                setUploadError(null);
                // Refresh data after successful upload
                await fetchData();
                // Clear success message after 3 seconds
                setTimeout(() => setUploadSuccess(false), 3000);
            } else {
                setUploadError(response.data.error || 'Upload failed');
                setUploadSuccess(false);
            }
        } catch (err) {
            const message = err.response?.data?.error || err.response?.data?.details || err.message || 'Failed to upload file.';
            setUploadError(message);
            setUploadSuccess(false);
        } finally {
            setUploading(false);
            // Reset file input
            event.target.value = '';
        }
    };


    const formattedLastUpdated = lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Unknown';

    const hasData = displayRows.length > 0;

    const columnHeaders = useMemo(() => columns, [columns]);

    const tableColumnCount = columnHeaders.length;

    return (
        <div className="w-full min-h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-8 px-4" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-[95%] mx-auto w-full" style={{ width: '100%' }}>
                <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
                    <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-8 py-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <h1 className="text-3xl font-bold text-white">Drafting Work Load</h1>

                            </div>
                            <div>
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

                    <div className="p-6 space-y-4">
                        <div className="bg-gradient-to-r from-gray-50 to-accent-50 rounded-xl p-4 border border-gray-200 shadow-sm">
                            <div className="flex flex-col gap-3">
                                <div className="grid grid-cols-2 gap-3">
                                    <div className="flex flex-col gap-3">
                                        <div>
                                            <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                                🎯 Ball In Court
                                            </label>
                                            <div className="grid grid-cols-8 gap-1">
                                                <button
                                                    onClick={() => setSelectedBallInCourt(ALL_OPTION_VALUE)}
                                                    className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedBallInCourt === ALL_OPTION_VALUE
                                                        ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                        : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                        }`}
                                                    title="All"
                                                >
                                                    All
                                                </button>
                                                {ballInCourtOptions.map((option) => (
                                                    <button
                                                        key={option}
                                                        onClick={() => setSelectedBallInCourt(option)}
                                                        className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedBallInCourt === option
                                                            ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                            : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                            }`}
                                                        title={option}
                                                    >
                                                        {option}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                        <div>
                                            <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                                👤 Submittal Manager
                                            </label>
                                            <div className="grid grid-cols-8 gap-1">
                                                <button
                                                    onClick={() => setSelectedSubmittalManager(ALL_OPTION_VALUE)}
                                                    className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedSubmittalManager === ALL_OPTION_VALUE
                                                        ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                        : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                        }`}
                                                    title="All"
                                                >
                                                    All
                                                </button>
                                                {submittalManagerOptions.map((option) => (
                                                    <button
                                                        key={option}
                                                        onClick={() => setSelectedSubmittalManager(option)}
                                                        className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedSubmittalManager === option
                                                            ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                            : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                            }`}
                                                        title={option}
                                                    >
                                                        {option}
                                                    </button>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                                            📁 Project Name
                                        </label>
                                        <div className="grid grid-cols-8 gap-1">
                                            <button
                                                onClick={() => setSelectedProjectName(ALL_OPTION_VALUE)}
                                                className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedProjectName === ALL_OPTION_VALUE
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
                                                    className={`px-0.5 py-0.5 rounded text-xs font-medium shadow-sm transition-all truncate ${selectedProjectName === option
                                                        ? 'bg-accent-500 text-white hover:bg-accent-600'
                                                        : 'bg-white border border-gray-300 text-gray-700 hover:bg-accent-50 hover:border-accent-300'
                                                        }`}
                                                    title={option}
                                                >
                                                    {option}
                                                </button>
                                            ))}
                                        </div>
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
                                <div className="mt-4 bg-green-50 border-l-4 border-green-500 text-green-700 px-4 py-3 rounded-lg shadow-sm">
                                    <div className="flex items-start">
                                        <span className="text-xl mr-3">✓</span>
                                        <div>
                                            <p className="font-semibold">File uploaded successfully!</p>
                                            <p className="text-sm mt-1">The data has been refreshed.</p>
                                        </div>
                                    </div>
                                </div>
                            )}
                            {uploadError && (
                                <div className="mt-4 bg-red-50 border-l-4 border-red-500 text-red-700 px-4 py-3 rounded-lg shadow-sm">
                                    <div className="flex items-start">
                                        <span className="text-xl mr-3">⚠️</span>
                                        <div>
                                            <p className="font-semibold">Upload failed</p>
                                            <p className="text-sm mt-1">{uploadError}</p>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>

                        {loading && (
                            <div className="text-center py-12">
                                <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                                <p className="text-gray-600 font-medium">Loading Drafting Work Load data...</p>
                            </div>
                        )}

                        {error && !loading && (
                            <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-6 py-4 rounded-lg shadow-sm">
                                <div className="flex items-start">
                                    <span className="text-xl mr-3">⚠️</span>
                                    <div>
                                        <p className="font-semibold">Unable to load Drafting Work Load data</p>
                                        <p className="text-sm mt-1">{error}</p>
                                    </div>
                                </div>
                            </div>
                        )}

                        {!loading && !error && (
                            <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
                                <div className="">
                                    <table className="w-full" style={{ borderCollapse: 'collapse' }}>
                                        <thead className="bg-gray-100">
                                            <tr>
                                                {columnHeaders.map((column) => {
                                                    const isOrderNumber = column === 'Order Number';
                                                    const isNotes = column === 'Notes';
                                                    const isProjectName = column === 'Project Name';

                                                    if (isProjectName) {
                                                        return (
                                                            <th
                                                                key={column}
                                                                className="px-2 py-0.5 text-center text-xs font-bold text-gray-900 uppercase tracking-wider bg-gray-100 border-r border-gray-300"
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

                                                    return (
                                                        <th
                                                            key={column}
                                                            className={`${isOrderNumber ? 'px-1 py-0.5 w-16' : 'px-2 py-0.5'} ${isNotes ? 'w-40' : ''} text-center text-xs font-bold text-gray-900 uppercase tracking-wider bg-gray-100 border-r border-gray-300`}
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
                                                        columns={columnHeaders}
                                                        formatCellValue={formatCellValue}
                                                        formatDate={formatDate}
                                                        onOrderNumberChange={handleOrderNumberChange}
                                                        onNotesChange={handleNotesChange}
                                                        onStatusChange={handleStatusChange}
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

export default DraftingWorkLoad;

function TableRow({ row, columns, formatCellValue, formatDate, onOrderNumberChange, onNotesChange, onStatusChange, rowIndex }) {
    const [editingOrderNumber, setEditingOrderNumber] = useState(false);
    const [orderNumberValue, setOrderNumberValue] = useState('');
    const [editingNotes, setEditingNotes] = useState(false);
    const [notesValue, setNotesValue] = useState('');
    const inputRef = useRef(null);
    const notesInputRef = useRef(null);

    const submittalId = row['Submittals Id'] || row.submittal_id;

    const formatTypeValue = (value) => {
        if (value === null || value === undefined || value === '') {
            return value;
        }
        const typeMap = {
            'Submittal For Gc  Approval': 'Sub GC',
            'Drafting Release Review': 'DRR'
        };
        return typeMap[value] || value;
    };

    const handleOrderNumberFocus = () => {
        // Check if this row has multiple assignees (comma-separated ball_in_court)
        const ballInCourt = row.ball_in_court ?? row['Ball In Court'] ?? '';
        const hasMultipleAssignees = String(ballInCourt).includes(',');

        // Don't allow editing order number for multiple assignees (reviewers)
        if (hasMultipleAssignees) {
            return;
        }

        const currentValue = row['Order Number'] ?? row.order_number ?? '';
        setOrderNumberValue(currentValue === null || currentValue === undefined ? '' : String(currentValue));
        setEditingOrderNumber(true);
    };

    const handleOrderNumberBlur = () => {
        setEditingOrderNumber(false);
        if (submittalId && onOrderNumberChange) {
            onOrderNumberChange(submittalId, orderNumberValue);
        }
    };

    const handleOrderNumberKeyDown = (e) => {
        if (e.key === 'Enter') {
            e.target.blur();
        } else if (e.key === 'Escape') {
            const currentValue = row['Order Number'] ?? row.order_number ?? '';
            setOrderNumberValue(currentValue === null || currentValue === undefined ? '' : String(currentValue));
            setEditingOrderNumber(false);
        }
    };

    const handleNotesFocus = () => {
        const currentValue = row['Notes'] ?? row.notes ?? '';
        setNotesValue(currentValue === null || currentValue === undefined ? '' : String(currentValue));
        setEditingNotes(true);
    };

    const handleNotesBlur = () => {
        setEditingNotes(false);
        if (submittalId && onNotesChange) {
            onNotesChange(submittalId, notesValue);
        }
    };

    const handleNotesKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            e.target.blur();
        } else if (e.key === 'Escape') {
            const currentValue = row['Notes'] ?? row.notes ?? '';
            setNotesValue(currentValue === null || currentValue === undefined ? '' : String(currentValue));
            setEditingNotes(false);
        }
    };

    useEffect(() => {
        if (editingOrderNumber && inputRef.current) {
            inputRef.current.focus();
            inputRef.current.select();
        }
    }, [editingOrderNumber]);

    useEffect(() => {
        if (editingNotes && notesInputRef.current) {
            notesInputRef.current.focus();
            notesInputRef.current.select();
        }
    }, [editingNotes]);

    const rowType = row.type ?? row['Type'] ?? '';
    const isDraftingReleaseReview = rowType === 'Drafting Release Review';

    // Alternate row background colors
    const rowBgClass = rowIndex % 2 === 0 ? 'bg-white' : 'bg-gray-50';

    return (
        <tr
            className={`${rowBgClass} hover:bg-gray-100 transition-colors duration-150 border-b border-gray-300`}
        >
            {columns.map((column) => {
                const isOrderNumber = column === 'Order Number';
                const isSubmittalId = column === 'Submittals Id';
                const isType = column === 'Type';
                const isNotes = column === 'Notes';
                const isStatus = column === 'Status';

                // Defi// Custom width for Submittals Id and Project Number
                let customWidthClass = '';
                if (isSubmittalId) {
                    customWidthClass = 'w-24'; // Accommodate 8-10 digit ID
                } else if (column === 'Project Number') {
                    customWidthClass = 'w-20'; // Accommodate 3-4 digit number
                } else if (column === 'Title') {
                    customWidthClass = 'w-48'; // Give Title a fixed width to help with wrapping
                } else if (column === 'Submittal Manager') {
                    customWidthClass = 'w-32'; // Reduce Submittal Manager width
                }

                // Apply Type truncation mapping before formatting
                let rawValue = row[column];
                if (isType) {
                    rawValue = formatTypeValue(rawValue);
                }
                let cellValue = formatCellValue(rawValue);

                if (isOrderNumber && editingOrderNumber) {
                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-1 py-0.5 align-middle ${rowBgClass} border-r border-gray-300 text-center`}
                        >
                            <input
                                ref={inputRef}
                                type="text"
                                value={orderNumberValue}
                                onChange={(e) => setOrderNumberValue(e.target.value)}
                                onBlur={handleOrderNumberBlur}
                                onKeyDown={handleOrderNumberKeyDown}
                                className="w-full px-0.5 py-0 text-xs border-2 border-accent-500 rounded-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 bg-white font-medium text-gray-900"
                                style={{ minWidth: '30px', maxWidth: '50px' }}
                            />
                        </td>
                    );
                }

                if (isOrderNumber) {
                    // Check if this row has multiple assignees (comma-separated ball_in_court)
                    const ballInCourt = row.ball_in_court ?? row['Ball In Court'] ?? '';
                    const hasMultipleAssignees = String(ballInCourt).includes(',');
                    const isEditable = !hasMultipleAssignees;

                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-1 py-0.5 align-middle ${rowBgClass} border-r border-gray-300 text-center`}
                            onClick={isEditable ? handleOrderNumberFocus : undefined}
                            title={isEditable ? "Click to edit order number" : "Order number editing disabled for multiple assignees (reviewers)"}
                        >
                            <div className={`px-0.5 py-0 text-xs border rounded-sm font-medium min-w-[20px] max-w-[50px] inline-block transition-colors ${isEditable
                                ? 'border-gray-300 bg-gray-50 hover:bg-white hover:border-accent-400 cursor-text text-gray-700'
                                : 'border-gray-200 bg-gray-100 cursor-not-allowed text-gray-500 opacity-75'
                                }`}>
                                {cellValue}
                            </div>
                        </td>
                    );
                }

                if (isNotes && editingNotes) {
                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-2 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300`}
                            style={{ width: '160px' }}
                        >
                            <textarea
                                ref={notesInputRef}
                                value={notesValue}
                                onChange={(e) => setNotesValue(e.target.value)}
                                onBlur={handleNotesBlur}
                                onKeyDown={handleNotesKeyDown}
                                className="w-full px-1 py-0.5 text-xs border-2 border-accent-500 rounded-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 bg-white text-gray-900 resize-none shadow-sm transition-all text-center"
                                rows={1}
                                placeholder="Add notes..."
                                style={{ lineHeight: '1.5' }}
                            />
                        </td>
                    );
                }

                if (isNotes) {
                    const hasNotes = cellValue && cellValue !== '—';
                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-2 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300`}
                            style={{ width: '160px' }}
                            onClick={handleNotesFocus}
                            title="Click to edit notes"
                        >
                            <div className={`px-0.5 py-0 text-xs rounded-sm border transition-all cursor-text min-h-[10px] text-center ${hasNotes
                                ? 'border-gray-200 bg-gray-50 hover:bg-white hover:border-accent-300 hover:shadow-sm text-gray-800'
                                : 'border-gray-200 bg-gray-50/50 hover:bg-gray-100 hover:border-accent-300 text-gray-500'
                                }`}>
                                {hasNotes ? (
                                    <div className="whitespace-normal break-words leading-tight">
                                        {cellValue}
                                    </div>
                                ) : (
                                    <span className="italic">Click to add notes...</span>
                                )}
                            </div>
                        </td>
                    );
                }

                if (isSubmittalId && cellValue !== '—') {
                    const projectId = row['Project Id'] ?? row.procore_project_id ?? '';
                    const submittalId = row['Submittals Id'] ?? row.submittal_id ?? '';
                    const href = projectId && submittalId
                        ? `https://app.procore.com/webclients/host/companies/18521/projects/${projectId}/tools/submittals/${submittalId}`
                        : '#';

                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-2 py-0.5 whitespace-nowrap text-xs align-middle font-medium ${rowBgClass} border-r border-gray-300 ${customWidthClass} text-center`}
                            title={cellValue}
                        >
                            {href !== '#' ? (
                                <a
                                    href={href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-blue-600 hover:text-blue-800 underline font-semibold inline-flex items-center gap-1 text-xs"
                                >
                                    <span>{cellValue}</span>
                                </a>
                            ) : (
                                <span className="text-gray-900 text-xs">{cellValue}</span>
                            )}
                        </td>
                    );
                }

                if (isStatus) {
                    const currentStatus = row.submittal_drafting_status ?? row['Submittal Drafting Status'] ?? 'STARTED';
                    const statusOptions = ['STARTED', 'NEED VIF', 'HOLD'];

                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className={`px-2 py-0.5 align-middle text-center ${rowBgClass} border-r border-gray-300`}
                        >
                            <select
                                value={currentStatus}
                                onChange={(e) => {
                                    if (submittalId && onStatusChange) {
                                        onStatusChange(submittalId, e.target.value);
                                    }
                                }}
                                className="w-full px-1 py-0.5 text-xs border border-gray-300 rounded bg-white text-gray-900 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 text-center"
                            >
                                {statusOptions.map((option) => (
                                    <option key={option} value={option}>
                                        {option}
                                    </option>
                                ))}
                            </select>
                        </td>
                    );
                }

                // Apply light green background for Type cell when type is "Drafting Release Review"
                const cellBgClass = isType && isDraftingReleaseReview
                    ? 'bg-green-100'
                    : rowBgClass;

                // Determine if this column should allow text wrapping
                const shouldWrap = column === 'Title' || column === 'Notes';
                const whitespaceClass = shouldWrap ? 'whitespace-normal' : 'whitespace-nowrap';

                return (
                    <td
                        key={`${row.id}-${column}`}
                        className={`px-2 py-0.5 ${whitespaceClass} text-xs align-middle font-medium ${cellBgClass} border-r border-gray-300 ${customWidthClass} text-center`}
                        title={cellValue}
                    >
                        {cellValue}
                    </td>
                );
            })}
        </tr>
    );
}

