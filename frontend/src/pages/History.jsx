import { useState } from 'react';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function History() {
    const [job, setJob] = useState('');
    const [release, setRelease] = useState('');
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [submitted, setSubmitted] = useState(false);
    const [searchMetadata, setSearchMetadata] = useState(null);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!job && !release) {
            setError('Please enter at least one: Job Number or Release');
            return;
        }

        setLoading(true);
        setError(null);
        setSubmitted(true);

        try {
            const params = {};
            if (job) params.job = parseInt(job);
            if (release) params.release = release;

            const response = await axios.get(`${API_BASE_URL}/jobs/history`, { params });
            setHistory(response.data.history || []);
            // Store search metadata for display
            setSearchMetadata({
                searchType: response.data.search_type,
                searchJob: response.data.search_job,
                searchRelease: response.data.search_release,
                jobReleases: response.data.job_releases || []
            });
        } catch (err) {
            setError(err.response?.data?.error || err.message);
            setHistory([]);
            setSearchMetadata(null);
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
        <div className="w-full min-h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-8 px-4" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-7xl mx-auto w-full" style={{ width: '100%', maxWidth: '1280px' }}>
                <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
                    <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-8 py-6">
                        <div className="flex justify-between items-center">
                            <div>
                                <h1 className="text-3xl font-bold text-white mb-2">Job Change History</h1>
                                <p className="text-accent-100">Track and analyze job changes over time</p>
                            </div>
                        </div>
                    </div>

                    <div className="p-8">

                        <form onSubmit={handleSubmit} className="bg-gradient-to-r from-accent-50 to-blue-50 rounded-xl p-6 mb-6 border border-accent-200 shadow-sm">
                            <div className="mb-4">
                                <p className="text-sm text-gray-600 mb-2">
                                    💡 <strong>Search options:</strong> Enter Job Number, Release, or both to find change history
                                </p>
                            </div>
                            <div className="flex flex-wrap gap-4 items-end">
                                <div className="flex-1 min-w-[200px]">
                                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                                        🔢 Job Number <span className="text-gray-400 font-normal">(optional)</span>
                                    </label>
                                    <input
                                        type="number"
                                        value={job}
                                        onChange={(e) => setJob(e.target.value)}
                                        placeholder="e.g., 123"
                                        className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-base focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white shadow-sm transition-all"
                                    />
                                </div>
                                <div className="flex-1 min-w-[200px]">
                                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                                        📦 Release <span className="text-gray-400 font-normal">(optional)</span>
                                    </label>
                                    <input
                                        type="text"
                                        value={release}
                                        onChange={(e) => setRelease(e.target.value)}
                                        placeholder="e.g., 1"
                                        className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-base focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white shadow-sm transition-all"
                                    />
                                </div>
                                <div className="min-w-[180px]">
                                    <button
                                        type="submit"
                                        className="w-full px-6 py-2.5 bg-gradient-to-r from-accent-500 to-accent-600 hover:from-accent-600 hover:to-accent-700 text-white font-semibold rounded-lg shadow-md hover:shadow-lg transition-all duration-200 transform hover:scale-105 disabled:opacity-60 disabled:cursor-not-allowed disabled:transform-none disabled:hover:shadow-md"
                                        disabled={loading}
                                    >
                                        {loading ? (
                                            <span className="flex items-center justify-center">
                                                <span className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></span>
                                                Loading...
                                            </span>
                                        ) : (
                                            '🔍 View History'
                                        )}
                                    </button>
                                </div>
                            </div>
                        </form>

                        {error && (
                            <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-6 py-4 rounded-lg mb-6 shadow-sm">
                                <div className="flex items-center">
                                    <span className="text-xl mr-3">⚠️</span>
                                    <div>
                                        <p className="font-semibold">Error loading history</p>
                                        <p className="text-sm mt-1">{error}</p>
                                    </div>
                                </div>
                            </div>
                        )}

                        {submitted && !loading && !error && (
                            <>
                                <div className="bg-gradient-to-r from-accent-50 to-blue-50 rounded-xl p-6 mb-6 border border-accent-200">
                                    <h2 className="text-2xl font-bold text-gray-800 mb-2">
                                        {searchMetadata?.searchType === 'both'
                                            ? `History for Job ${searchMetadata.searchJob}-${searchMetadata.searchRelease}`
                                            : searchMetadata?.searchType === 'job'
                                                ? `History for Job #${searchMetadata.searchJob}`
                                                : `History for Release ${searchMetadata.searchRelease}`
                                        }
                                    </h2>
                                    <div className="flex items-center gap-4 flex-wrap">
                                        <div className="bg-white px-4 py-2 rounded-lg shadow-sm border border-accent-200">
                                            <p className="text-sm text-gray-600">
                                                Total changes: <span className="font-bold text-accent-700">{history.length}</span>
                                            </p>
                                        </div>
                                        {searchMetadata?.jobReleases && searchMetadata.jobReleases.length > 1 && (
                                            <div className="bg-white px-4 py-2 rounded-lg shadow-sm border border-accent-200">
                                                <p className="text-sm text-gray-600">
                                                    Job-Release combinations: <span className="font-bold text-accent-700">{searchMetadata.jobReleases.length}</span>
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                    {searchMetadata?.jobReleases && searchMetadata.jobReleases.length > 1 && (
                                        <div className="mt-4 pt-4 border-t border-accent-200">
                                            <p className="text-sm font-semibold text-gray-700 mb-2">Found Job-Release combinations:</p>
                                            <div className="flex flex-wrap gap-2">
                                                {searchMetadata.jobReleases.map((jr, idx) => (
                                                    <span
                                                        key={idx}
                                                        className="bg-white px-3 py-1 rounded-lg text-sm font-medium text-gray-700 border border-accent-200"
                                                    >
                                                        {jr.job}-{jr.release}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {history.length === 0 ? (
                                    <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
                                        <div className="text-gray-400 text-5xl mb-4">📭</div>
                                        <p className="text-gray-500 font-medium text-lg">No change history found</p>
                                        <p className="text-gray-400 text-sm mt-2">
                                            {searchMetadata?.searchType === 'both'
                                                ? `for job ${searchMetadata.searchJob}-${searchMetadata.searchRelease}`
                                                : searchMetadata?.searchType === 'job'
                                                    ? `for job #${searchMetadata.searchJob}`
                                                    : `for release ${searchMetadata.searchRelease}`
                                            }
                                        </p>
                                    </div>
                                ) : (
                                    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                                        <div className="overflow-x-auto">
                                            <table className="w-full">
                                                <thead className="bg-gradient-to-r from-gray-50 to-accent-50">
                                                    <tr>
                                                        {(searchMetadata?.searchType !== 'both') && (
                                                            <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Job-Release</th>
                                                        )}
                                                        <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Changed At</th>
                                                        <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Change Type</th>
                                                        <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Field</th>
                                                        <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">From</th>
                                                        <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">To</th>
                                                        <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Source</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="bg-white divide-y divide-gray-200">
                                                    {history.map((entry, index) => (
                                                        <tr
                                                            key={entry.id}
                                                            className="hover:bg-accent-50/50 transition-colors duration-150"
                                                            style={{ animationDelay: `${index * 30}ms` }}
                                                        >
                                                            {(searchMetadata?.searchType !== 'both') && (
                                                                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                                                    <span className="bg-accent-100 text-accent-800 px-2 py-1 rounded font-semibold">
                                                                        {entry.job}-{entry.release}
                                                                    </span>
                                                                </td>
                                                            )}
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                                                                {formatDateTime(entry.changed_at)}
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap">
                                                                <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${getChangeTypeColor(entry.change_type)}`}>
                                                                    {entry.change_type}
                                                                </span>
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                                                {entry.field_name}
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm">
                                                                {entry.from_value ? (
                                                                    <span className="bg-red-50 text-red-700 px-2 py-1 rounded font-medium">
                                                                        {entry.from_value}
                                                                    </span>
                                                                ) : (
                                                                    <span className="text-gray-400">-</span>
                                                                )}
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm">
                                                                {entry.to_value ? (
                                                                    <span className="bg-green-50 text-green-700 px-2 py-1 rounded font-medium">
                                                                        {entry.to_value}
                                                                    </span>
                                                                ) : (
                                                                    <span className="text-gray-400">-</span>
                                                                )}
                                                            </td>
                                                            <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                                                {entry.source}
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

export default History;