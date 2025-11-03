import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function Operations() {
    const navigate = useNavigate();
    const [operations, setOperations] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedDate, setSelectedDate] = useState('');
    const [availableDates, setAvailableDates] = useState([]);
    const [limit, setLimit] = useState(50);

    useEffect(() => {
        fetchOperations();
        fetchAvailableDates();
    }, [selectedDate, limit]);

    const fetchAvailableDates = async () => {
        try {
            const response = await axios.get(`${API_BASE_URL}/sync/operations?limit=200`);
            const dates = [...new Set(
                response.data.operations.map(op =>
                    new Date(op.started_at).toISOString().split('T')[0]
                )
            )].sort().reverse();
            setAvailableDates(dates);
            if (!selectedDate && dates.length > 0) {
                setSelectedDate(dates[0]);
            }
        } catch (err) {
            console.error('Error fetching dates:', err);
        }
    };

    const fetchOperations = async () => {
        setLoading(true);
        setError(null);
        try {
            const params = { limit };
            if (selectedDate) {
                params.start = selectedDate;
                params.end = selectedDate;
            }
            const response = await axios.get(`${API_BASE_URL}/sync/operations`, { params });
            setOperations(response.data.operations || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const formatDateTime = (dateString) => {
        return new Date(dateString).toLocaleString();
    };

    const getStatusColor = (status) => {
        const colors = {
            'completed': 'bg-green-100 text-green-800',
            'failed': 'bg-red-100 text-red-800',
            'pending': 'bg-yellow-100 text-yellow-800',
        };
        return colors[status] || 'bg-gray-100 text-gray-800';
    };

    return (
        <div className="w-full min-h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-8 px-4" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-7xl mx-auto w-full" style={{ width: '100%', maxWidth: '1280px' }}>
                <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
                    <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-8 py-6">
                        <div className="flex justify-between items-center">
                            <div>
                                <h1 className="text-3xl font-bold text-white mb-2">Sync Operations</h1>
                                <p className="text-accent-100">Monitor and track synchronization operations</p>
                            </div>
                        </div>
                    </div>

                    <div className="p-8">

                        <div className="bg-gradient-to-r from-gray-50 to-accent-50 rounded-xl p-6 mb-6 border border-gray-200">
                            <div className="flex flex-wrap gap-4 items-end">
                                <div className="flex-1 min-w-[200px]">
                                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                                        📅 Filter by Date
                                    </label>
                                    <select
                                        value={selectedDate}
                                        onChange={(e) => setSelectedDate(e.target.value)}
                                        className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white shadow-sm transition-all"
                                    >
                                        <option value="">All Dates</option>
                                        {availableDates.map(date => (
                                            <option key={date} value={date}>{date}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="min-w-[150px]">
                                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                                        🔢 Results Limit
                                    </label>
                                    <input
                                        type="number"
                                        min="1"
                                        max="200"
                                        value={limit}
                                        onChange={(e) => setLimit(parseInt(e.target.value))}
                                        className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white shadow-sm transition-all"
                                    />
                                </div>
                            </div>
                        </div>

                        {loading && (
                            <div className="text-center py-12">
                                <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                                <p className="text-gray-600 font-medium">Loading operations...</p>
                            </div>
                        )}
                        {error && (
                            <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-6 py-4 rounded-lg mb-6 shadow-sm">
                                <div className="flex items-center">
                                    <span className="text-xl mr-3">⚠️</span>
                                    <div>
                                        <p className="font-semibold">Error loading operations</p>
                                        <p className="text-sm mt-1">{error}</p>
                                    </div>
                                </div>
                            </div>
                        )}

                        {!loading && !error && (
                            <>
                                <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                                    <div className="overflow-x-auto">
                                        <table className="w-full">
                                            <thead className="bg-gradient-to-r from-gray-50 to-accent-50">
                                                <tr>
                                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Started</th>
                                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Operation ID</th>
                                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Type</th>
                                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Status</th>
                                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Source</th>
                                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Duration (s)</th>
                                                    <th className="px-6 py-4 text-center text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Actions</th>
                                                </tr>
                                            </thead>
                                            <tbody className="bg-white divide-y divide-gray-200">
                                                {operations.length === 0 ? (
                                                    <tr>
                                                        <td colSpan="7" className="px-6 py-12 text-center">
                                                            <div className="text-gray-400 text-4xl mb-3">📭</div>
                                                            <p className="text-gray-500 font-medium">No operations found</p>
                                                        </td>
                                                    </tr>
                                                ) : (
                                                    operations.map((op, index) => (
                                                        <tr
                                                            key={op.operation_id}
                                                            className="hover:bg-accent-50/50 transition-colors duration-150"
                                                            style={{ animationDelay: `${index * 50}ms` }}
                                                        >
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                                                                {formatDateTime(op.started_at)}
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap">
                                                                <span className="font-mono text-xs bg-gray-100 px-2 py-1 rounded text-gray-800">
                                                                    {op.operation_id}
                                                                </span>
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                                                {op.operation_type}
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap">
                                                                <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${getStatusColor(op.status)}`}>
                                                                    {op.status}
                                                                </span>
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                                                {op.source_system} {op.source_id || ''}
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700 font-medium">
                                                                {(op.duration_seconds || 0).toFixed(2)}s
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-center">
                                                                <button
                                                                    onClick={() => navigate(`/operations/${op.operation_id}/logs`)}
                                                                    className="inline-flex items-center px-3 py-1.5 bg-indigo-500 hover:bg-indigo-600 text-white text-xs font-medium rounded-md transition-colors duration-150 shadow-sm hover:shadow"
                                                                >
                                                                    📋 Logs
                                                                </button>
                                                            </td>
                                                        </tr>
                                                    ))
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                                <div className="mt-6 flex items-center justify-between">
                                    <div className="bg-accent-50 rounded-lg px-4 py-2 border border-accent-200">
                                        <p className="text-sm font-semibold text-accent-700">
                                            Total: <span className="text-accent-900">{operations.length}</span> operations
                                        </p>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Operations;