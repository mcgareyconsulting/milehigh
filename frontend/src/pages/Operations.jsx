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
        <div className="min-h-screen p-8 bg-gray-50">
            <div className="max-w-7xl mx-auto bg-white p-8 rounded-lg shadow-md">
                <div className="flex justify-between items-center mb-8">
                    <h1 className="text-3xl font-bold text-gray-800">Sync Operations</h1>
                    <button
                        className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded text-sm"
                        onClick={() => navigate('/')}
                    >
                        ← Back to Dashboard
                    </button>
                </div>

                <div className="flex gap-4 mb-6 items-end">
                    <label className="flex flex-col gap-1 text-sm text-gray-600">
                        Date:
                        <select
                            value={selectedDate}
                            onChange={(e) => setSelectedDate(e.target.value)}
                            className="px-3 py-2 border border-gray-300 rounded text-sm"
                        >
                            <option value="">All Dates</option>
                            {availableDates.map(date => (
                                <option key={date} value={date}>{date}</option>
                            ))}
                        </select>
                    </label>
                    <label className="flex flex-col gap-1 text-sm text-gray-600">
                        Limit:
                        <input
                            type="number"
                            min="1"
                            max="200"
                            value={limit}
                            onChange={(e) => setLimit(parseInt(e.target.value))}
                            className="px-3 py-2 border border-gray-300 rounded text-sm w-24"
                        />
                    </label>
                </div>

                {loading && (
                    <div className="text-center py-8 text-gray-600">Loading operations...</div>
                )}
                {error && (
                    <div className="bg-red-100 text-red-800 px-4 py-3 rounded mb-4">
                        Error: {error}
                    </div>
                )}

                {!loading && !error && (
                    <>
                        <div className="overflow-x-auto mb-4">
                            <table className="w-full border-collapse">
                                <thead>
                                    <tr className="bg-gray-50">
                                        <th className="px-4 py-3 text-left font-semibold text-gray-700 border-b">Started</th>
                                        <th className="px-4 py-3 text-left font-semibold text-gray-700 border-b">Operation ID</th>
                                        <th className="px-4 py-3 text-left font-semibold text-gray-700 border-b">Type</th>
                                        <th className="px-4 py-3 text-left font-semibold text-gray-700 border-b">Status</th>
                                        <th className="px-4 py-3 text-left font-semibold text-gray-700 border-b">Source</th>
                                        <th className="px-4 py-3 text-left font-semibold text-gray-700 border-b">Duration (s)</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {operations.length === 0 ? (
                                        <tr>
                                            <td colSpan="6" className="px-4 py-8 text-center text-gray-500">
                                                No operations found
                                            </td>
                                        </tr>
                                    ) : (
                                        operations.map((op) => (
                                            <tr key={op.operation_id} className="hover:bg-gray-50 border-b">
                                                <td className="px-4 py-3">{formatDateTime(op.started_at)}</td>
                                                <td className="px-4 py-3 font-mono text-sm">{op.operation_id}</td>
                                                <td className="px-4 py-3">{op.operation_type}</td>
                                                <td className="px-4 py-3">
                                                    <span className={`px-2 py-1 rounded text-xs font-medium ${getStatusColor(op.status)}`}>
                                                        {op.status}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3 text-gray-600 text-sm">
                                                    {op.source_system} {op.source_id || ''}
                                                </td>
                                                <td className="px-4 py-3">{(op.duration_seconds || 0).toFixed(2)}</td>
                                            </tr>
                                        ))
                                    )}
                                </tbody>
                            </table>
                        </div>
                        <p className="text-sm text-gray-600">Total: {operations.length}</p>
                    </>
                )}
            </div>
        </div>
    );
}

export default Operations;