import { useState, useEffect, useMemo, useCallback } from 'react';
import axios from 'axios';
import { DndContext, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { SortableContext, useSortable, arrayMove, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const ALL_OPTION_VALUE = '__ALL__';

const interpolateChannel = (start, end, factor) => Math.round(start + (end - start) * factor);

const interpolateColor = (startHex, endHex, factor) => {
    const parseHex = (hex) => {
        const sanitized = hex.replace('#', '');
        return {
            r: parseInt(sanitized.slice(0, 2), 16),
            g: parseInt(sanitized.slice(2, 4), 16),
            b: parseInt(sanitized.slice(4, 6), 16),
        };
    };

    const startColor = parseHex(startHex);
    const endColor = parseHex(endHex);

    const r = interpolateChannel(startColor.r, endColor.r, factor);
    const g = interpolateChannel(startColor.g, endColor.g, factor);
    const b = interpolateChannel(startColor.b, endColor.b, factor);

    return `rgb(${r}, ${g}, ${b})`;
};

function DraftingWorkLoad() {
    const [rows, setRows] = useState([]);
    const [columns, setColumns] = useState([]);
    const [selectedBallInCourt, setSelectedBallInCourt] = useState(ALL_OPTION_VALUE);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [uploadError, setUploadError] = useState(null);
    const [uploadSuccess, setUploadSuccess] = useState(false);

    const sensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: { distance: 4 }
        })
    );

    const fetchData = async () => {
        setLoading(true);
        setError(null);

        try {
            const response = await axios.get(`${API_BASE_URL}/procore/api/drafting-work-load`);
            console.log(response);
            const data = response.data || {};

            const cleanedRows = (data.submittals || []).map((row, index) => {
                const rawId = row.submittal_id ?? row.id ?? `row-${index}`;
                return {
                    ...row,
                    id: String(rawId)
                };
            });

            const visibleColumns = (data.columns && data.columns.length > 0
                ? data.columns
                : (cleanedRows[0] ? Object.keys(cleanedRows[0]) : [])
            ).filter((column) => column !== 'Response');

            setRows(cleanedRows);
            setColumns(visibleColumns);
            setLastUpdated(data.last_updated || null);
        } catch (err) {
            const message = err.response?.data?.error || err.message || 'Failed to load Drafting Work Load data.';
            setError(message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const matchesSelectedFilter = useCallback((row) => {
        if (selectedBallInCourt === ALL_OPTION_VALUE) {
            return true;
        }
        const value = row.ball_in_court;
        return (value ?? '').toString().trim() === selectedBallInCourt;
    }, [selectedBallInCourt]);

    const displayRows = useMemo(() => rows.filter(matchesSelectedFilter), [rows, matchesSelectedFilter]);

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

    const resetFilters = () => {
        setSelectedBallInCourt(ALL_OPTION_VALUE);
    };

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

    const handleDragEnd = useCallback((event) => {
        const { active, over } = event;
        if (!over || active.id === over.id) {
            return;
        }

        setRows((currentRows) => {
            const filteredWithIndex = currentRows
                .map((row, index) => ({ row, index }))
                .filter(({ row }) => matchesSelectedFilter(row));

            const activeIndex = filteredWithIndex.findIndex(({ row }) => row.id === active.id);
            const overIndex = filteredWithIndex.findIndex(({ row }) => row.id === over.id);

            if (activeIndex === -1 || overIndex === -1) {
                return currentRows;
            }

            const subsetRows = filteredWithIndex.map(({ row }) => row);
            const reorderedSubset = arrayMove(subsetRows, activeIndex, overIndex);

            const updatedRows = [...currentRows];
            filteredWithIndex.forEach(({ index }, position) => {
                updatedRows[index] = reorderedSubset[position];
            });

            return updatedRows;
        });
    }, [matchesSelectedFilter]);

    const formattedLastUpdated = lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Unknown';

    const hasData = displayRows.length > 0;

    const columnHeaders = useMemo(() => columns, [columns]);

    const orderLabels = useMemo(() => {
        const counters = new Map();
        return displayRows.reduce((acc, row) => {
            const key = (row['Ball In Court'] ?? '').toString();
            const currentCount = counters.get(key) ?? 0;
            acc[row.id] = currentCount < 10 ? currentCount : null;
            counters.set(key, currentCount + 1);
            return acc;
        }, {});
    }, [displayRows]);

    const tableColumnCount = columnHeaders.length + 2; // drag handle + order column

    const urgencyStyles = useMemo(() => {
        if (!hasData) {
            return {};
        }

        const total = displayRows.length;
        const lowUrgencyBackground = '#DCFCE7';
        const highUrgencyBackground = '#FEE2E2';
        const lowUrgencyBorder = '#34D399';
        const highUrgencyBorder = '#F87171';

        return displayRows.reduce((acc, row, index) => {
            const factor = total <= 1 ? 0 : index / (total - 1);
            const backgroundColor = interpolateColor(highUrgencyBackground, lowUrgencyBackground, factor);
            const borderColor = interpolateColor(highUrgencyBorder, lowUrgencyBorder, factor);

            acc[row.id] = {
                backgroundColor,
                borderLeft: `4px solid ${borderColor}`,
            };

            return acc;
        }, {});
    }, [displayRows, hasData]);

    const handleOrderInputChange = useCallback((rowId, orderValue) => {
        setRows((currentRows) => {
            const currentIndex = currentRows.findIndex((row) => row.id === rowId);
            if (currentIndex === -1) {
                return currentRows;
            }

            const currentRow = currentRows[currentIndex];
            const ballInCourtValue = (currentRow['Ball In Court'] ?? '').toString();

            const groupEntries = currentRows
                .map((row, index) => ({ row, index }))
                .filter(({ row }) => (row['Ball In Court'] ?? '').toString() === ballInCourtValue);

            const currentGroupIndex = groupEntries.findIndex(({ index }) => index === currentIndex);
            if (currentGroupIndex === -1) {
                return currentRows;
            }

            const maxPosition = Math.min(groupEntries.length - 1, 9);
            const clampedOrder = Math.max(0, Math.min(orderValue, maxPosition));

            const reorderedGroup = groupEntries.map(({ row }) => row);
            const [movedRow] = reorderedGroup.splice(currentGroupIndex, 1);
            reorderedGroup.splice(clampedOrder, 0, movedRow);

            const updatedRows = [...currentRows];
            groupEntries.forEach(({ index }, position) => {
                updatedRows[index] = reorderedGroup[position];
            });

            return updatedRows;
        });
    }, []);

    return (
        <div className="w-full min-h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-8 px-4" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-7xl mx-auto w-full" style={{ width: '100%', maxWidth: '1280px' }}>
                <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
                    <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-8 py-6">
                        <h1 className="text-3xl font-bold text-white">Drafting Work Load</h1>
                        <p className="text-accent-100 mt-2">View and filter drafting workload by Ball In Court.</p>
                    </div>

                    <div className="p-8 space-y-6">
                        <div className="bg-gradient-to-r from-gray-50 to-accent-50 rounded-xl p-6 border border-gray-200 shadow-sm">
                            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
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
                                <div className="overflow-x-auto">
                                    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
                                        <SortableContext items={displayRows.map((row) => row.id)} strategy={verticalListSortingStrategy}>
                                            <table className="w-full">
                                                <thead className="bg-gradient-to-r from-gray-50 to-accent-50">
                                                    <tr>
                                                        <th className="px-4 py-3 w-12 border-b border-gray-200 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                                            {/* drag handle header */}
                                                        </th>
                                                        <th className="px-4 py-3 w-16 border-b border-gray-200 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                                            Order
                                                        </th>
                                                        {columnHeaders.map((column) => (
                                                            <th
                                                                key={column}
                                                                className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200"
                                                            >
                                                                {column}
                                                            </th>
                                                        ))}
                                                    </tr>
                                                </thead>
                                                <tbody className="bg-white divide-y divide-gray-200">
                                                    {!hasData ? (
                                                        <tr>
                                                            <td
                                                                colSpan={tableColumnCount}
                                                                className="px-6 py-12 text-center text-gray-500 font-medium"
                                                            >
                                                                No records match the selected filters.
                                                            </td>
                                                        </tr>
                                                    ) : (
                                                        displayRows.map((row) => (
                                                            <SortableRow
                                                                key={row.id}
                                                                row={row}
                                                                columns={columnHeaders}
                                                                formatCellValue={formatCellValue}
                                                                urgencyStyle={urgencyStyles[row.id]}
                                                                orderLabel={orderLabels[row.id]}
                                                                onOrderChange={handleOrderInputChange}
                                                            />
                                                        ))
                                                    )}
                                                </tbody>
                                            </table>
                                        </SortableContext>
                                    </DndContext>
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

function SortableRow({ row, columns, formatCellValue, urgencyStyle, orderLabel, onOrderChange }) {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging
    } = useSortable({ id: row.id });

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        backgroundColor: isDragging ? 'rgba(226, 232, 240, 0.5)' : urgencyStyle?.backgroundColor,
        borderLeft: urgencyStyle?.borderLeft,
    };

    return (
        <tr
            ref={setNodeRef}
            style={style}
            className="hover:bg-accent-50/50 transition-colors duration-150"
        >
            <td className="px-4 py-4 align-top text-gray-400" {...attributes} {...listeners}>
                <span className="cursor-grab select-none text-xl leading-none" aria-hidden="true">
                    ☰
                </span>
                <span className="sr-only">Reorder row</span>
            </td>
            <td className="px-4 py-4 align-top">
                <input
                    type="number"
                    min="0"
                    max="9"
                    value={orderLabel !== null && orderLabel !== undefined ? orderLabel : ''}
                    placeholder="—"
                    onChange={(event) => {
                        const value = event.target.value;
                        if (value === '') {
                            return;
                        }
                        const parsed = Number.parseInt(value, 10);
                        if (!Number.isNaN(parsed)) {
                            const clamped = Math.max(0, Math.min(parsed, 9));
                            onOrderChange(row.id, clamped);
                        }
                    }}
                    className="no-spin w-14 px-3 py-1.5 text-center border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent text-sm font-semibold text-gray-700 bg-white/90 placeholder:text-gray-400"
                />
            </td>
            {columns.map((column) => (
                <td
                    key={`${row.id}-${column}`}
                    className="px-6 py-4 whitespace-pre-wrap text-sm text-gray-700 align-top"
                >
                    {formatCellValue(row[column])}
                </td>
            ))}
        </tr>
    );
}

