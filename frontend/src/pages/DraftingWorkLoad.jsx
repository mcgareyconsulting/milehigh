import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import axios from 'axios';
import { io } from 'socket.io-client';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const ALL_OPTION_VALUE = '__ALL__';

function DraftingWorkLoad() {
    const [rows, setRows] = useState([]);
    const [columns, setColumns] = useState([]);
    const [selectedBallInCourt, setSelectedBallInCourt] = useState(ALL_OPTION_VALUE);
    const [selectedSubmittalManager, setSelectedSubmittalManager] = useState(ALL_OPTION_VALUE);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [uploadError, setUploadError] = useState(null);
    const [uploadSuccess, setUploadSuccess] = useState(false);
    const socketRef = useRef(null);

    const fetchData = useCallback(async (silent = false) => {
        if (!silent) {
            setLoading(true);
        }
        setError(null);

        try {
            const response = await axios.get(`${API_BASE_URL}/procore/api/drafting-work-load`);
            const data = response.data || {};

            const submittals = data.submittals || [];

            const cleanedRows = submittals.map((submittal, index) => {
                const rawId = submittal.submittal_id ?? submittal.id ?? `row-${index}`;

                // Map database field names to frontend expected names
                return {
                    ...submittal,
                    'Submittals Id': submittal.submittal_id,
                    'Project Id': submittal.procore_project_id,
                    'Submittal Manager': submittal.submittal_manager,
                    'Project Name': submittal.project_name,
                    'Project Number': submittal.project_number,
                    'Title': submittal.title,
                    'Status': submittal.status,
                    'Type': submittal.type,
                    'Ball In Court': submittal.ball_in_court,
                    'Order Number': submittal.order_number,
                    'Notes': submittal.notes,
                    id: String(rawId)
                };
            });

            // Sort by order_number (nulls last), then by submittal_id
            cleanedRows.sort((a, b) => {
                const orderA = a.order_number ?? a['Order Number'] ?? 999999;
                const orderB = b.order_number ?? b['Order Number'] ?? 999999;
                if (orderA !== orderB) {
                    return orderA - orderB;
                }
                return (a['Submittals Id'] || '').localeCompare(b['Submittals Id'] || '');
            });

            // Define the desired column order (Project Id is tracked but hidden from display)
            const desiredColumnOrder = [
                'Order Number',
                'Submittals Id',
                'Project Number',
                'Project Name',
                'Title',
                'Ball In Court',
                'Type',
                'Status',
                'Submittal Manager',
                'Notes'
            ];

            // Get all available columns from the data
            const allColumns = data.columns && data.columns.length > 0
                ? data.columns
                : (cleanedRows[0] ? Object.keys(cleanedRows[0]) : []);

            // Filter and order columns according to desired order
            const visibleColumns = desiredColumnOrder.filter(column =>
                allColumns.includes(column) || cleanedRows.some(row => row[column] !== undefined)
            );

            setRows(cleanedRows);
            setColumns(visibleColumns);

            const mostRecentUpdate = cleanedRows.length > 0
                ? cleanedRows.reduce((latest, row) => {
                    const rowDate = row.last_updated ? new Date(row.last_updated) : null;
                    return rowDate && (!latest || rowDate > latest) ? rowDate : latest;
                }, null)
                : null;
            setLastUpdated(mostRecentUpdate ? mostRecentUpdate.toISOString() : null);
        } catch (err) {
            const message = err.response?.data?.error || err.message || 'Failed to load Drafting Work Load data.';
            setError(message);
        } finally {
            if (!silent) {
                setLoading(false);
            }
        }
    }, []);

    useEffect(() => {
        fetchData();
    }, [fetchData]);

    // Setup websocket connection for real-time updates
    useEffect(() => {
        // Create socket connection
        socketRef.current = io(API_BASE_URL, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionAttempts: 5
        });

        socketRef.current.on('connect', () => {
            console.log('WebSocket connected');
        });

        socketRef.current.on('disconnect', () => {
            console.log('WebSocket disconnected');
        });

        socketRef.current.on('ball_in_court_updated', (data) => {
            console.log('Ball in court updated:', data);
            // Reload data silently (no loading spinner)
            fetchData(true);
        });

        // Cleanup on unmount
        return () => {
            if (socketRef.current) {
                socketRef.current.disconnect();
            }
        };
    }, [fetchData]);

    const matchesSelectedFilter = useCallback((row) => {
        // Check Ball In Court filter
        if (selectedBallInCourt !== ALL_OPTION_VALUE) {
            const ballInCourtValue = row.ball_in_court;
            if ((ballInCourtValue ?? '').toString().trim() !== selectedBallInCourt) {
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

        return true;
    }, [selectedBallInCourt, selectedSubmittalManager]);

    const displayRows = useMemo(() => {
        const filtered = rows.filter(matchesSelectedFilter);

        // Sort by Ball In Court, then by order_number (as float)
        return filtered.sort((a, b) => {
            const ballA = (a.ball_in_court ?? '').toString();
            const ballB = (b.ball_in_court ?? '').toString();

            if (ballA !== ballB) {
                return ballA.localeCompare(ballB);
            }

            // Sort by order_number as float (nulls last)
            const orderA = a.order_number ?? a['Order Number'] ?? 999999;
            const orderB = b.order_number ?? b['Order Number'] ?? 999999;
            return orderA - orderB;
        });
    }, [rows, matchesSelectedFilter]);

    const ballInCourtOptions = useMemo(() => {
        const values = new Set();
        rows.forEach((row) => {
            const value = row.ball_in_court;
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                values.add(String(value).trim());
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

    const handleBallInCourtChange = (event) => {
        setSelectedBallInCourt(event.target.value);
    };

    const handleSubmittalManagerChange = (event) => {
        setSelectedSubmittalManager(event.target.value);
    };

    const resetFilters = () => {
        setSelectedBallInCourt(ALL_OPTION_VALUE);
        setSelectedSubmittalManager(ALL_OPTION_VALUE);
    };

    const handleOrderNumberChange = useCallback(async (submittalId, newValue) => {
        // Parse the value as float
        const parsedValue = newValue === '' || newValue === null || newValue === undefined
            ? null
            : parseFloat(newValue);

        // Validate it's a number if not null
        if (parsedValue !== null && isNaN(parsedValue)) {
            return; // Invalid input, don't update
        }

        try {
            await axios.put(`${API_BASE_URL}/procore/api/drafting-work-load/order`, {
                submittal_id: submittalId,
                order_number: parsedValue
            });

            // Refresh data to get updated order
            await fetchData(true);
        } catch (err) {
            console.error(`Failed to update order for ${submittalId}:`, err);
            // Refresh to get correct state
            await fetchData(true);
        }
    }, [fetchData]);

    const handleNotesChange = useCallback(async (submittalId, newValue) => {
        try {
            await axios.put(`${API_BASE_URL}/procore/api/drafting-work-load/notes`, {
                submittal_id: submittalId,
                notes: newValue
            });

            // Refresh data to get updated notes
            await fetchData(true);
        } catch (err) {
            console.error(`Failed to update notes for ${submittalId}:`, err);
            // Refresh to get correct state
            await fetchData(true);
        }
    }, [fetchData]);


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
                    <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-8 py-6">
                        <h1 className="text-3xl font-bold text-white">Drafting Work Load</h1>
                        <p className="text-accent-100 mt-2">View and filter drafting workload by Ball In Court and Submittal Manager.</p>
                    </div>

                    <div className="p-8 space-y-6">
                        <div className="bg-gradient-to-r from-gray-50 to-accent-50 rounded-xl p-6 border border-gray-200 shadow-sm">
                            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                                <div className="flex flex-col gap-4 md:flex-row md:flex-1">
                                    <div className="flex-1 min-w-[200px]">
                                        <label className="block text-sm font-semibold text-gray-700 mb-2">
                                            🎯 Filter by Ball In Court
                                        </label>
                                        <select
                                            value={selectedBallInCourt}
                                            onChange={handleBallInCourtChange}
                                            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white shadow-sm transition-all"
                                        >
                                            <option value={ALL_OPTION_VALUE}>All</option>
                                            {ballInCourtOptions.map((option) => (
                                                <option key={option} value={option}>
                                                    {option}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="flex-1 min-w-[200px]">
                                        <label className="block text-sm font-semibold text-gray-700 mb-2">
                                            👤 Filter by Submittal Manager
                                        </label>
                                        <select
                                            value={selectedSubmittalManager}
                                            onChange={handleSubmittalManagerChange}
                                            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white shadow-sm transition-all"
                                        >
                                            <option value={ALL_OPTION_VALUE}>All</option>
                                            {submittalManagerOptions.map((option) => (
                                                <option key={option} value={option}>
                                                    {option}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                                <div className="flex gap-3">
                                    <button
                                        onClick={resetFilters}
                                        className="px-5 py-2.5 bg-white border border-accent-300 text-accent-700 rounded-lg font-medium shadow-sm hover:bg-accent-50 transition-all"
                                    >
                                        Reset Filters
                                    </button>
                                    <div className="px-5 py-2.5 bg-white border border-gray-200 text-gray-600 rounded-lg font-medium shadow-sm">
                                        Total: <span className="text-gray-900">{displayRows.length}</span> records
                                    </div>
                                </div>
                            </div>
                            <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                <div className="text-sm text-gray-500">
                                    Last updated: <span className="font-medium text-gray-700">{formattedLastUpdated}</span>
                                </div>
                                <div className="flex items-center gap-3">
                                    <label className="relative cursor-pointer">
                                        <input
                                            type="file"
                                            accept=".xlsx,.xls"
                                            onChange={handleFileUpload}
                                            disabled={uploading}
                                            className="hidden"
                                            id="file-upload"
                                        />
                                        <span className={`inline-flex items-center px-5 py-2.5 rounded-lg font-medium shadow-sm transition-all ${uploading
                                            ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                                            : 'bg-accent-500 text-white hover:bg-accent-600 cursor-pointer'
                                            }`}>
                                            {uploading ? (
                                                <>
                                                    <span className="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></span>
                                                    Uploading...
                                                </>
                                            ) : (
                                                <>
                                                    📤 Upload Excel File
                                                </>
                                            )}
                                        </span>
                                    </label>
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
                                <div className="overflow-x-hidden">
                                    <table className="w-full" style={{ borderCollapse: 'collapse', tableLayout: 'fixed', width: '100%' }}>
                                        <thead className="bg-gray-100">
                                            <tr>
                                                {columnHeaders.map((column) => {
                                                    const isOrderNumber = column === 'Order Number';
                                                    const isNotes = column === 'Notes';
                                                    let widthClass = '';
                                                    if (isOrderNumber) {
                                                        widthClass = 'w-24';
                                                    } else if (isNotes) {
                                                        widthClass = 'w-1/4'; // 25% width for Notes
                                                    }
                                                    return (
                                                        <th
                                                            key={column}
                                                            className={`${isOrderNumber ? 'px-3 py-3' : 'px-6 py-4'} ${widthClass} text-left text-xs font-bold text-gray-900 uppercase tracking-wider bg-gray-100`}
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
                                                displayRows.map((row) => (
                                                    <TableRow
                                                        key={row.id}
                                                        row={row}
                                                        columns={columnHeaders}
                                                        formatCellValue={formatCellValue}
                                                        formatDate={formatDate}
                                                        onOrderNumberChange={handleOrderNumberChange}
                                                        onNotesChange={handleNotesChange}
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

function TableRow({ row, columns, formatCellValue, formatDate, onOrderNumberChange, onNotesChange }) {
    const [editingOrderNumber, setEditingOrderNumber] = useState(false);
    const [orderNumberValue, setOrderNumberValue] = useState('');
    const [editingNotes, setEditingNotes] = useState(false);
    const [notesValue, setNotesValue] = useState('');
    const inputRef = useRef(null);
    const notesInputRef = useRef(null);

    const submittalId = row['Submittals Id'] || row.submittal_id;

    const handleOrderNumberFocus = () => {
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

    return (
        <tr
            className="bg-white hover:opacity-90 transition-colors duration-150 border-b border-gray-200"
        >
            {columns.map((column) => {
                const isOrderNumber = column === 'Order Number';
                const isSubmittalId = column === 'Submittals Id';
                const isType = column === 'Type';
                const isNotes = column === 'Notes';

                let cellValue = formatCellValue(row[column]);

                if (isOrderNumber && editingOrderNumber) {
                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className="px-3 py-3 align-middle bg-white"
                        >
                            <input
                                ref={inputRef}
                                type="text"
                                value={orderNumberValue}
                                onChange={(e) => setOrderNumberValue(e.target.value)}
                                onBlur={handleOrderNumberBlur}
                                onKeyDown={handleOrderNumberKeyDown}
                                className="w-full px-2 py-1.5 text-sm border-2 border-accent-500 rounded-md focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 bg-white font-medium text-gray-900"
                                style={{ minWidth: '60px', maxWidth: '80px' }}
                            />
                        </td>
                    );
                }

                if (isOrderNumber) {
                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className="px-3 py-3 align-middle bg-white"
                            onClick={handleOrderNumberFocus}
                            title="Click to edit order number"
                        >
                            <div className="px-2 py-1.5 text-sm border border-gray-300 rounded-md bg-gray-50 hover:bg-white hover:border-accent-400 cursor-text transition-colors font-medium text-gray-700 min-w-[60px] max-w-[80px] inline-block">
                                {cellValue}
                            </div>
                        </td>
                    );
                }

                if (isNotes && editingNotes) {
                    return (
                        <td
                            key={`${row.id}-${column}`}
                            className="px-6 py-4 align-top bg-white"
                            style={{ width: '25%' }}
                        >
                            <textarea
                                ref={notesInputRef}
                                value={notesValue}
                                onChange={(e) => setNotesValue(e.target.value)}
                                onBlur={handleNotesBlur}
                                onKeyDown={handleNotesKeyDown}
                                className="w-full px-3 py-2.5 text-sm border-2 border-accent-500 rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-600 bg-white text-gray-900 resize-none shadow-sm transition-all"
                                rows={6}
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
                            className="px-6 py-4 align-top bg-white"
                            style={{ width: '25%' }}
                            onClick={handleNotesFocus}
                            title="Click to edit notes"
                        >
                            <div className={`px-3 py-2.5 text-sm rounded-lg border transition-all cursor-text min-h-[120px] ${hasNotes
                                ? 'border-gray-200 bg-gray-50 hover:bg-white hover:border-accent-300 hover:shadow-sm text-gray-800'
                                : 'border-gray-200 bg-gray-50/50 hover:bg-gray-100 hover:border-accent-300 text-gray-500'
                                }`}>
                                {hasNotes ? (
                                    <div className="whitespace-pre-wrap break-words leading-relaxed">
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
                            className="px-6 py-4 whitespace-pre-wrap text-sm align-top font-medium bg-white"
                        >
                            {href !== '#' ? (
                                <a
                                    href={href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-blue-600 hover:text-blue-800 underline font-semibold inline-flex items-center gap-1"
                                >
                                    <span>{cellValue}</span>
                                </a>
                            ) : (
                                <span className="text-gray-900">{cellValue}</span>
                            )}
                        </td>
                    );
                }

                // Apply light green background for Type cell when type is "Drafting Release Review"
                const cellBgClass = isType && isDraftingReleaseReview
                    ? 'bg-green-100'
                    : 'bg-white';

                return (
                    <td
                        key={`${row.id}-${column}`}
                        className={`px-6 py-4 whitespace-pre-wrap text-sm text-gray-900 align-top font-medium ${cellBgClass}`}
                    >
                        {cellValue}
                    </td>
                );
            })}
        </tr>
    );
}

