import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';

import { API_BASE_URL } from '../utils/api';

function Logs() {
    const navigate = useNavigate();
    const { operationId } = useParams();
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (operationId) {
            fetchLogs();
        }
    }, [operationId]);

    const fetchLogs = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/operations/${operationId}/logs`);
            setLogs(response.data.logs || []);
        } catch (err) {
            setError(err.response?.data?.error || err.message);
        } finally {
            setLoading(false);
        }
    };

    const formatDateTime = (dateString) => {
        return new Date(dateString).toLocaleString();
    };

    const getLevelColor = (level) => {
        const colors = {
            'ERROR': 'bg-red-100 text-red-800 border-red-300',
            'WARNING': 'bg-yellow-100 text-yellow-800 border-yellow-300',
            'INFO': 'bg-blue-100 text-blue-800 border-blue-300',
            'DEBUG': 'bg-gray-100 text-gray-800 border-gray-300',
        };
        return colors[level] || 'bg-gray-100 text-gray-800 border-gray-300';
    };

    const formatJsonData = (data) => {
        if (!data || (typeof data === 'object' && Object.keys(data).length === 0)) {
            return null;
        }
        try {
            if (typeof data === 'string') {
                return data;
            }

            // Return raw JSON without any modifications - show data as-is from the API
            return JSON.stringify(data, null, 2);
        } catch {
            return String(data);
        }
    };

    return (
        <div className="min-h-screen p-8 bg-gray-50">
            <div className="max-w-7xl mx-auto bg-white p-8 rounded-lg shadow-md">
                <div className="flex justify-between items-center mb-8">
                    <div>
                        <h1 className="text-3xl font-bold text-gray-800 mb-2">
                            Operation Logs
                        </h1>
                        <p className="text-gray-600 font-mono text-sm">Operation ID: {operationId}</p>
                    </div>
                    <button
                        className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded text-sm transition-colors"
                        onClick={() => navigate('/operations')}
                    >
                        ← Back to Operations
                    </button>
                </div>

                {loading && (
                    <div className="text-center py-12">
                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-500 mb-4"></div>
                        <p className="text-gray-600 font-medium">Loading logs...</p>
                    </div>
                )}

                {error && (
                    <div className="bg-red-100 text-red-800 px-4 py-3 rounded mb-4">
                        Error: {error}
                    </div>
                )}

                {!loading && !error && (
                    <>
                        <div className="mb-4 text-sm text-gray-600">
                            Total logs: {logs.length}
                        </div>

                        {logs.length === 0 ? (
                            <div className="text-center py-12 text-gray-500">
                                No logs found for this operation
                            </div>
                        ) : (
                            <div className="space-y-4">
                                {logs.map((log, index) => (
                                    <div
                                        key={index}
                                        className="border-l-4 border-gray-200 pl-4 py-3 bg-gray-50 rounded-r-lg hover:bg-gray-100 transition-colors"
                                    >
                                        <div className="flex items-start justify-between mb-2">
                                            <div className="flex items-center gap-2">
                                                <span className={`px-2 py-1 rounded text-xs font-semibold border ${getLevelColor(log.level)}`}>
                                                    {log.level}
                                                </span>
                                                <span className="text-xs text-gray-500 font-mono">
                                                    {formatDateTime(log.timestamp)}
                                                </span>
                                            </div>
                                        </div>
                                        <div className="text-sm font-medium text-gray-800 mb-2">
                                            {log.message}
                                        </div>
                                        {(() => {
                                            if (!log.data) return null;
                                            const formattedData = formatJsonData(log.data);
                                            if (!formattedData) return null;
                                            return (
                                                <pre className="bg-gray-900 text-green-400 p-4 rounded-lg text-xs overflow-x-auto mt-2 font-mono whitespace-pre-wrap">
                                                    {formattedData}
                                                </pre>
                                            );
                                        })()}
                                    </div>
                                ))}
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}

export default Logs;