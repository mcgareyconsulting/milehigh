import { useState } from 'react';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function History() {
    const [job, setJob] = useState('');
    const [release, setRelease] = useState('');
    const [history, setHistory] = useState([]);
    const [jobDetails, setJobDetails] = useState([]);
    const [selectedJobKey, setSelectedJobKey] = useState(null);
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
        setJobDetails([]);
        setSelectedJobKey(null);
        setHistory([]);
        setSearchMetadata(null);

        try {
            const params = {};
            if (job) params.job = parseInt(job);
            if (release) params.release = release;

            const response = await axios.get(`${API_BASE_URL}/api/jobs/history`, { params });
            const historyData = response.data.history || [];
            setHistory(historyData);

            const jobDetailsPayload = response.data.job_details || [];
            setJobDetails(jobDetailsPayload);

            const defaultSelection = response.data.default_selection;
            if (defaultSelection) {
                setSelectedJobKey(`${defaultSelection.job}-${defaultSelection.release}`);
            } else if (jobDetailsPayload.length > 0) {
                const first = jobDetailsPayload[0];
                setSelectedJobKey(`${first.job}-${first.release}`);
            }

            // Store search metadata for display
            setSearchMetadata({
                searchType: response.data.search_type,
                searchJob: response.data.search_job,
                searchRelease: response.data.search_release,
                jobReleases: response.data.job_releases || [],
                totalChanges: response.data.total_changes ?? historyData.length,
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

    const getChangeTypeColor = (action) => {
        if (!action) return 'bg-gray-100 text-gray-800';

        const actionLower = action.toLowerCase();
        const colors = {
            'update': 'bg-blue-100 text-blue-800',
            'update_stage': 'bg-blue-100 text-blue-800',
            'create': 'bg-green-100 text-green-800',
            'created': 'bg-green-100 text-green-800',
            'delete': 'bg-red-100 text-red-800',
            'list_move': 'bg-purple-100 text-purple-800',
        };
        // Try exact match first, then check first part of action (e.g., 'update' from 'update_stage')
        return colors[actionLower] || colors[actionLower.split('_')[0]] || 'bg-gray-100 text-gray-800';
    };

    const filteredHistory = selectedJobKey
        ? history.filter((entry) => `${entry.job}-${entry.release}` === selectedJobKey)
        : history;

    const selectedJobDetails = selectedJobKey
        ? jobDetails.find((detail) => `${detail.job}-${detail.release}` === selectedJobKey)
        : null;
    const hasJobDetails = jobDetails.length > 0;

    const formatDate = (dateString) => {
        if (!dateString) {
            return '—';
        }
        const date = new Date(dateString);
        if (Number.isNaN(date.getTime())) {
            return dateString;
        }
        return date.toLocaleDateString();
    };

    const getNotFoundMessage = () => {
        if (!searchMetadata) {
            return 'No results found for your search.';
        }
        if (searchMetadata.searchType === 'both' && searchMetadata.searchJob && searchMetadata.searchRelease) {
            return `No job found for ${searchMetadata.searchJob}-${searchMetadata.searchRelease}.`;
        }
        if (searchMetadata.searchType === 'job' && searchMetadata.searchJob) {
            return `No jobs found for Job #${searchMetadata.searchJob}.`;
        }
        if (searchMetadata.searchType === 'release' && searchMetadata.searchRelease) {
            return `No jobs found for Release ${searchMetadata.searchRelease}.`;
        }
        return 'No results found for your search.';
    };

    return (
        <div className="w-full min-h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-8 px-4" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-7xl mx-auto w-full" style={{ width: '100%', maxWidth: '1280px' }}>
                <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
                    <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-8 py-6">
                        <div className="flex justify-between items-center">
                            <div>
                                <h1 className="text-3xl font-bold text-white mb-2">Job Search</h1>
                                <p className="text-accent-100">Find jobs and review their change history</p>
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
                                        {selectedJobKey && (
                                            <div className="bg-white px-4 py-2 rounded-lg shadow-sm border border-accent-200">
                                                <p className="text-sm text-gray-600">
                                                    Showing: <span className="font-bold text-accent-700">{filteredHistory.length}</span>
                                                </p>
                                            </div>
                                        )}
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
                                                {searchMetadata.jobReleases.map((jr) => {
                                                    const key = `${jr.job}-${jr.release}`;
                                                    const isActive = key === selectedJobKey;
                                                    return (
                                                        <button
                                                            key={key}
                                                            type="button"
                                                            onClick={() => setSelectedJobKey(key)}
                                                            className={`px-3 py-1 rounded-lg text-sm font-medium border transition ${isActive
                                                                ? 'bg-accent-500 text-white border-accent-500 shadow'
                                                                : 'bg-white text-gray-700 border-accent-200 hover:bg-accent-50'
                                                                }`}
                                                        >
                                                            {jr.job}-{jr.release}
                                                        </button>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {!hasJobDetails && history.length === 0 ? (
                                    <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
                                        <div className="text-gray-400 text-5xl mb-4">📭</div>
                                        <p className="text-gray-500 font-medium text-lg">No change history found</p>
                                        <p className="text-gray-400 text-sm mt-2">
                                            {getNotFoundMessage()}
                                        </p>
                                    </div>
                                ) : (
                                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                                        <div className="lg:col-span-1">
                                            <div className="bg-white border border-accent-200 rounded-xl shadow-sm p-6 h-full">
                                                <h3 className="text-xl font-semibold text-gray-800">
                                                    {selectedJobDetails ? `${selectedJobDetails.job}-${selectedJobDetails.release}` : 'Select a job-release'}
                                                </h3>
                                                {selectedJobDetails ? (
                                                    <>
                                                        <p className="text-gray-500 mt-1">{selectedJobDetails.job_name}</p>
                                                        <dl className="mt-6 space-y-4 text-sm text-gray-600">
                                                            <div>
                                                                <dt className="font-semibold text-gray-700">Description</dt>
                                                                <dd>{selectedJobDetails.description || '—'}</dd>
                                                            </div>
                                                            <div>
                                                                <dt className="font-semibold text-gray-700">Install Hours</dt>
                                                                <dd>{selectedJobDetails.install_hrs ?? '—'}</dd>
                                                            </div>
                                                            <div>
                                                                <dt className="font-semibold text-gray-700">Start Install Date</dt>
                                                                <dd>{formatDate(selectedJobDetails.start_install)}</dd>
                                                            </div>
                                                            <div>
                                                                <dt className="font-semibold text-gray-700">Trello List</dt>
                                                                <dd>{selectedJobDetails.trello_list_name || '—'}</dd>
                                                            </div>
                                                        </dl>
                                                        {selectedJobDetails.viewer_url && (
                                                            <a
                                                                href={selectedJobDetails.viewer_url}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="mt-6 inline-flex items-center px-4 py-2 rounded-lg bg-accent-500 text-white font-semibold hover:bg-accent-600 transition"
                                                            >
                                                                Open Viewer
                                                            </a>
                                                        )}
                                                    </>
                                                ) : (
                                                    <p className="text-gray-500 mt-4 text-sm">
                                                        Choose a job-release to view its details and related changes.
                                                    </p>
                                                )}
                                            </div>
                                        </div>
                                        <div className="lg:col-span-2">
                                            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                                                <div className="overflow-x-auto">
                                                    <table className="w-full">
                                                        <thead className="bg-gradient-to-r from-gray-50 to-accent-50">
                                                            <tr>
                                                                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Created At</th>
                                                                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Applied At</th>
                                                                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Action</th>
                                                                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">New Value</th>
                                                                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Source</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody className="bg-white divide-y divide-gray-200">
                                                            {filteredHistory.length === 0 ? (
                                                                <tr>
                                                                    <td colSpan={searchMetadata?.searchType !== 'both' ? 7 : 6} className="px-6 py-6 text-center text-sm text-gray-500">
                                                                        No change history for the selected job-release.
                                                                    </td>
                                                                </tr>
                                                            ) : (
                                                                filteredHistory.map((entry, index) => (
                                                                    <tr
                                                                        key={entry.id}
                                                                        className="hover:bg-accent-50/50 transition-colors duration-150"
                                                                        style={{ animationDelay: `${index * 30}ms` }}
                                                                    >
                                                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                                                                            {formatDateTime(entry.created_at)}
                                                                        </td>
                                                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                                                                            {formatDateTime(entry.applied_at)}
                                                                        </td>
                                                                        <td className="px-6 py-4 whitespace-nowrap">
                                                                            <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${getChangeTypeColor(entry.action)}`}>
                                                                                {entry.action || 'unknown'}
                                                                            </span>
                                                                        </td>
                                                                        <td className="px-6 py-4 text-sm">
                                                                            {entry.new_value ? (
                                                                                <span className="bg-green-50 text-green-700 px-2 py-1 rounded font-medium whitespace-normal break-words max-w-md">
                                                                                    {entry.new_value}
                                                                                </span>
                                                                            ) : (
                                                                                <span className="text-gray-400">-</span>
                                                                            )}
                                                                        </td>
                                                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                                                                            {entry.source}
                                                                        </td>
                                                                    </tr>
                                                                ))
                                                            )}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </div>
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