import { useState, useEffect, useMemo } from 'react';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const ALL_OPTION_VALUE = '__ALL__';

function DraftingWorkLoad() {
    const [rows, setRows] = useState([]);
    const [columns, setColumns] = useState([]);
    const [ballInCourtOptions, setBallInCourtOptions] = useState([]);
    const [selectedBallInCourt, setSelectedBallInCourt] = useState(ALL_OPTION_VALUE);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastUpdated, setLastUpdated] = useState(null);

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            setError(null);

            try {
                const params = {};
                if (selectedBallInCourt !== ALL_OPTION_VALUE) {
                    params.ball_in_court = selectedBallInCourt;
                }

                const response = await axios.get(`${API_BASE_URL}/api/drafting-work-load`, { params });
                const data = response.data || {};

                setRows(data.rows || []);
                setColumns(data.columns || []);
                setBallInCourtOptions(data.ball_in_court_options || []);
                setLastUpdated(data.last_updated || null);
            } catch (err) {
                const message = err.response?.data?.error || err.message || 'Failed to load Drafting Work Load data.';
                setError(message);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [selectedBallInCourt]);

    const effectiveColumns = useMemo(() => {
        if (columns && columns.length > 0) {
            return columns;
        }
        if (rows.length > 0) {
            return Object.keys(rows[0]);
        }
        return [];
    }, [columns, rows]);

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

    const formattedLastUpdated = lastUpdated ? new Date(lastUpdated).toLocaleString() : 'Unknown';

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
                                        Total: <span className="text-gray-900">{rows.length}</span> records
                                    </div>
                                </div>
                            </div>
                            <div className="mt-4 text-sm text-gray-500">
                                Last updated: <span className="font-medium text-gray-700">{formattedLastUpdated}</span>
                            </div>
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
                                    <table className="w-full">
                                        <thead className="bg-gradient-to-r from-gray-50 to-accent-50">
                                            <tr>
                                                {effectiveColumns.map((column) => (
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
                                            {rows.length === 0 ? (
                                                <tr>
                                                    <td
                                                        colSpan={effectiveColumns.length || 1}
                                                        className="px-6 py-12 text-center text-gray-500 font-medium"
                                                    >
                                                        No records match the selected filters.
                                                    </td>
                                                </tr>
                                            ) : (
                                                rows.map((row, index) => {
                                                    const rowKey = row['Submittals Id'] ?? row.id ?? index;
                                                    return (
                                                        <tr key={rowKey} className="hover:bg-accent-50/50 transition-colors duration-150">
                                                            {effectiveColumns.map((column) => (
                                                                <td
                                                                    key={`${rowKey}-${column}`}
                                                                    className="px-6 py-4 whitespace-pre-wrap text-sm text-gray-700 align-top"
                                                                >
                                                                    {formatCellValue(row[column])}
                                                                </td>
                                                            ))}
                                                        </tr>
                                                    );
                                                })
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

