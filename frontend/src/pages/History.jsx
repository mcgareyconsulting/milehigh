import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function History() {
    const navigate = useNavigate();
    const [job, setJob] = useState('');
    const [release, setRelease] = useState('');
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [submitted, setSubmitted] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!job || !release) {
            setError('Please enter both Job and Release');
            return;
        }

        setLoading(true);
        setError(null);
        setSubmitted(true);

        try {
            const response = await axios.get(`${API_BASE_URL}/jobs/history`, {
                params: { job: parseInt(job), release }
            });
            setHistory(response.data.history || []);
        } catch (err) {
            setError(err.response?.data?.error || err.message);
            setHistory([]);
        } finally {
            setLoading(false);
        }
    };

    const formatDateTime = (dateString) => {
        return new Date(dateString).toLocaleString();
    };

    const getChangeTypeColor = (changeType) => {
        const colors = {
            'update': 'bg-blue-100 text-blue-800',
            'create': 'bg-green-100 text-green-800',
            'delete': 'bg-red-100 text-red-800',
        };
        return colors[changeType] || 'bg-gray-100 text-gray-800';
    };

    return (
        <div className="min-h-screen p-8 bg-gray-50">
            <div className="max-w-7xl mx-auto bg-white p-8 rounded-lg shadow-md">
                <div className="flex justify-between items-center mb-8">
                    <h1 className="text-3xl font-bold text-gray-800">Job Change History</h1>
                    <button
                        className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded text-sm transition-colors"
                        onClick={() => navigate('/')}
                    >
                        ← Back to Dashboard
                    </button>
                </div>

                <form onSubmit={handleSubmit} className="flex gap-4 mb-6 p-6 bg-gray-50 rounded-lg items-end">
                    <div className="flex flex-col gap-2">
                        <label className="font-medium text-gray-700 text-sm">
                            Job:
                        </label>
                        <input
                            type="number"
                            value={job}
                            onChange={(e) => setJob(e.target.value)}
                            placeholder="e.g., 123"
                            required
                            className="px-3 py-2 border border-gray-300 rounded text-base min-w-[150px] focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                        />
                    </div>
                    <div className="flex flex-col gap-2">
                        <label className="font-medium text-gray-700 text-sm">
                            Release:
                        </label>
                        <input
                            type="text"
                            value={release}
                            onChange={(e) => setRelease(e.target.value)}
                            placeholder="e.g., 1"
                            required
                            className="px-3 py-2 border border-gray-300 rounded text-base min-w-[150px] focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                        />
                    </div>
                    <button
                        type="submit"
                        className="px-8 py-2 bg-indigo-500 hover:bg-indigo-600 text-white font-semibold rounded transition-colors h-fit disabled:opacity-60 disabled:cursor-not-allowed"
                        disabled={loading}
                    >
                        {loading ? 'Loading...' : 'View History'}
                    </button>
                </form>

                {error && (
                    <div className="bg-red-100 text-red-800 px-4 py-3 rounded mb-4">
                        Error: {error}
                    </div>
                )}

                {submitted && !loading && !error && (
                    <>
                        <div className="mb-6">
                            <h2 className="text-2xl font-bold text-gray-800 mb-2">
                                History for Job {job}-{release}
                            </h2>
                            <p className="text-sm text-gray-600">Total changes: {history.length}</p>
                        </div>

                        {history.length === 0 ? (
                            <div className="text-center py-8 text-gray-500">
                                No change history found for this job-release
                            </div>
                        ) : (
                            <div className="overflow-x-auto mb-4">
                                <table className="w-full border-collapse">
                                    <thead>
                                        <tr className="bg-gray-50">
                                            <th className="px-4 py-3 text-left font-semibold text-gray-700 border-b">Changed At</th>
                                            <th className="px-4 py-3 text-left font-semibold text-gray-700 border-b">Change Type</th>
                                            <th className="px-4 py-3 text-left font-semibold text-gray-700 border-b">Field</th>
                                            <th className="px-4 py-3 text-left font-semibold text-gray-700 border-b">From</th>
                                            <th className="px-4 py-3 text-left font-semibold text-gray-700 border-b">To</th>
                                            <th className="px-4 py-3 text-left font-semibold text-gray-700 border-b">Source</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {history.map((entry) => (
                                            <tr key={entry.id} className="hover:bg-gray-50 border-b">
                                                <td className="px-4 py-3">{formatDateTime(entry.changed_at)}</td>
                                                <td className="px-4 py-3">
                                                    <span className={`px-2 py-1 rounded text-xs font-medium ${getChangeTypeColor(entry.change_type)}`}>
                                                        {entry.change_type}
                                                    </span>
                                                </td>
                                                <td className="px-4 py-3">{entry.field_name}</td>
                                                <td className="px-4 py-3 text-red-600 font-medium">{entry.from_value || '-'}</td>
                                                <td className="px-4 py-3 text-green-600 font-medium">{entry.to_value || '-'}</td>
                                                <td className="px-4 py-3 text-gray-600 text-sm">{entry.source}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}

export default History;