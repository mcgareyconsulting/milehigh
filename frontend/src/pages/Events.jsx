import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function Events() {
    const [searchParams, setSearchParams] = useSearchParams();
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [selectedDate, setSelectedDate] = useState('');
    const [availableDates, setAvailableDates] = useState([]);
    const [selectedSource, setSelectedSource] = useState('');
    const [availableSources, setAvailableSources] = useState([]);
    const [limit, setLimit] = useState(50);
    const [expandedPayload, setExpandedPayload] = useState({});
    const [submittalId, setSubmittalId] = useState(searchParams.get('submittal_id') || '');
    const [jobFilter, setJobFilter] = useState(searchParams.get('job') || '');
    const [releaseFilter, setReleaseFilter] = useState(searchParams.get('release') || '');

    useEffect(() => {
        // Update filters from URL params
        const urlSubmittalId = searchParams.get('submittal_id') || '';
        const urlJob = searchParams.get('job') || '';
        const urlRelease = searchParams.get('release') || '';
        setSubmittalId(urlSubmittalId);
        setJobFilter(urlJob);
        setReleaseFilter(urlRelease);
    }, [searchParams]);

    useEffect(() => {
        fetchEvents();
        fetchFilters();
    }, [selectedDate, limit, selectedSource, submittalId, jobFilter, releaseFilter]);

    const fetchFilters = async () => {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/events/filters`);
            const dates = [...new Set(
                response.data.dates
            )].sort().reverse();
            setAvailableDates(dates);
            const sources = response.data.sources;
            setAvailableSources(sources);
        } catch (err) {
            console.error('Error fetching filters:', err);
        }
    }

    const fetchEvents = async () => {
        setLoading(true);
        setError(null);
        try {
            const params = { limit };
            if (selectedDate) {
                params.start = selectedDate;
                params.end = selectedDate;
            }
            if (selectedSource) {
                params.source = selectedSource;
            }
            if (submittalId) {
                params.submittal_id = String(submittalId).trim();
            }
            if (jobFilter) {
                params.job = parseInt(jobFilter, 10);
            }
            if (releaseFilter) {
                params.release = String(releaseFilter).trim();
            }
            const response = await axios.get(`${API_BASE_URL}/brain/events`, { params });
            setEvents(response.data.events || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const formatDateTime = (dateString) => {
        if (!dateString) return '—';
        return new Date(dateString).toLocaleString();
    };

    const formatPayload = (payload) => {
        if (!payload) return '—';
        if (typeof payload === 'string') {
            try {
                payload = JSON.parse(payload);
            } catch {
                return payload;
            }
        }
        return JSON.stringify(payload, null, 2);
    };

    const togglePayload = (eventId) => {
        setExpandedPayload(prev => ({
            ...prev,
            [eventId]: !prev[eventId]
        }));
    };

    const getSourceColor = (source) => {
        const colors = {
            'Trello': 'bg-blue-100 text-blue-800',
            'Excel': 'bg-green-100 text-green-800',
            'System': 'bg-gray-100 text-gray-800',
            'Procore': 'bg-purple-100 text-purple-800',
        };
        return colors[source] || 'bg-gray-100 text-gray-800';
    };

    const resetFilters = () => {
        setSelectedDate('');
        setSelectedSource('');
        setLimit(50);
        setSubmittalId('');
        setJobFilter('');
        setReleaseFilter('');
        // Clear all filters from URL
        const newParams = new URLSearchParams(searchParams);
        newParams.delete('submittal_id');
        newParams.delete('job');
        newParams.delete('release');
        setSearchParams(newParams);
    };

    const clearSubmittalIdFilter = () => {
        setSubmittalId('');
        const newParams = new URLSearchParams(searchParams);
        newParams.delete('submittal_id');
        setSearchParams(newParams);
    };

    const clearJobReleaseFilter = () => {
        setJobFilter('');
        setReleaseFilter('');
        const newParams = new URLSearchParams(searchParams);
        newParams.delete('job');
        newParams.delete('release');
        setSearchParams(newParams);
    };

    return (
        <div className="w-full min-h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-8 px-4" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-7xl mx-auto w-full" style={{ width: '100%', maxWidth: '1280px' }}>
                <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
                    <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-8 py-6">
                        <div className="flex justify-between items-center">
                            <div>
                                <h1 className="text-3xl font-bold text-white mb-2">Job Events</h1>
                                <p className="text-accent-100">View and track job events with source, date, and payload information</p>
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
                                <div className="flex-1 min-w-[200px]">
                                    <label className="block text-sm font-semibold text-gray-700 mb-2">
                                        🔗 Filter by Source
                                    </label>
                                    <select
                                        value={selectedSource}
                                        onChange={(e) => setSelectedSource(e.target.value)}
                                        className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white shadow-sm transition-all"
                                    >
                                        <option value="">All Sources</option>
                                        {availableSources.map(source => (
                                            <option key={source} value={source}>{source}</option>
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
                                        onChange={(e) => {
                                            const value = e.target.value;
                                            if (value === '') {
                                                setLimit(50); // Default to 50 if empty
                                            } else {
                                                const parsed = parseInt(value, 10);
                                                if (!isNaN(parsed) && parsed >= 1 && parsed <= 200) {
                                                    setLimit(parsed);
                                                }
                                            }
                                        }}
                                        className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white shadow-sm transition-all"
                                    />
                                </div>
                                <div className="flex items-end">
                                    <button
                                        onClick={resetFilters}
                                        className="px-6 py-2.5 bg-gray-200 hover:bg-gray-300 text-gray-700 font-semibold rounded-lg text-sm transition-colors duration-150 shadow-sm hover:shadow border border-gray-300 flex items-center gap-2"
                                    >
                                        <span>🔄</span>
                                        Reset Filters
                                    </button>
                                </div>
                            </div>
                            {submittalId && (
                                <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <span className="text-blue-700 font-semibold">Filtered by Submittal ID:</span>
                                        <span className="text-blue-900 font-mono text-sm">{submittalId}</span>
                                    </div>
                                    <button
                                        onClick={clearSubmittalIdFilter}
                                        className="text-blue-700 hover:text-blue-900 font-medium text-sm underline"
                                    >
                                        Clear
                                    </button>
                                </div>
                            )}
                            {(jobFilter || releaseFilter) && (
                                <div className="mt-4 bg-green-50 border border-green-200 rounded-lg px-4 py-3 flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <span className="text-green-700 font-semibold">Filtered by Job:</span>
                                        <span className="text-green-900 font-mono text-sm">
                                            {jobFilter}{releaseFilter ? `-${releaseFilter}` : ''}
                                        </span>
                                    </div>
                                    <button
                                        onClick={clearJobReleaseFilter}
                                        className="text-green-700 hover:text-green-900 font-medium text-sm underline"
                                    >
                                        Clear
                                    </button>
                                </div>
                            )}
                        </div>

                        {loading && (
                            <div className="text-center py-12">
                                <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                                <p className="text-gray-600 font-medium">Loading events...</p>
                            </div>
                        )}
                        {error && (
                            <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-6 py-4 rounded-lg mb-6 shadow-sm">
                                <div className="flex items-center">
                                    <span className="text-xl mr-3">⚠️</span>
                                    <div>
                                        <p className="font-semibold">Error loading events</p>
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
                                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Date</th>
                                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Source</th>
                                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Identifier</th>
                                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Action</th>
                                                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200">Payload</th>
                                                </tr>
                                            </thead>
                                            <tbody className="bg-white divide-y divide-gray-200">
                                                {events.length === 0 ? (
                                                    <tr>
                                                        <td colSpan="5" className="px-6 py-12 text-center">
                                                            <div className="text-gray-400 text-4xl mb-3">📭</div>
                                                            <p className="text-gray-500 font-medium">No events found</p>
                                                        </td>
                                                    </tr>
                                                ) : (
                                                    events.map((event, index) => {
                                                        const uniqueKey = `${event.type}-${event.id}`;
                                                        return (
                                                            <tr
                                                                key={uniqueKey}
                                                                className="hover:bg-accent-50/50 transition-colors duration-150"
                                                                style={{ animationDelay: `${index * 50}ms` }}
                                                            >
                                                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                                                                    {formatDateTime(event.created_at)}
                                                                </td>
                                                                <td className="px-6 py-4 whitespace-nowrap">
                                                                    <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${getSourceColor(event.source)}`}>
                                                                        {event.source}
                                                                    </span>
                                                                </td>
                                                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
                                                                    {event.type === 'job'
                                                                        ? `${event.job}-${event.release || 'N/A'}`
                                                                        : event.submittal_id || 'N/A'
                                                                    }
                                                                </td>
                                                                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                                                                    {event.action}
                                                                </td>
                                                                <td className="px-6 py-4 text-sm">
                                                                    {expandedPayload[uniqueKey] ? (
                                                                        <div className="space-y-2">
                                                                            <pre className="bg-gray-50 p-3 rounded-lg text-xs overflow-x-auto max-w-md border border-gray-200">
                                                                                {formatPayload(event.payload)}
                                                                            </pre>
                                                                            <button
                                                                                onClick={() => togglePayload(uniqueKey)}
                                                                                className="text-xs text-accent-600 hover:text-accent-700 font-medium"
                                                                            >
                                                                                ▲ Collapse
                                                                            </button>
                                                                        </div>
                                                                    ) : (
                                                                        <button
                                                                            onClick={() => togglePayload(uniqueKey)}
                                                                            className="text-xs text-accent-600 hover:text-accent-700 font-medium"
                                                                        >
                                                                            ▼ View Payload
                                                                        </button>
                                                                    )}
                                                                </td>
                                                            </tr>
                                                        );
                                                    })
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                                <div className="mt-6 flex items-center justify-between">
                                    <div className="bg-accent-50 rounded-lg px-4 py-2 border border-accent-200">
                                        <p className="text-sm font-semibold text-accent-700">
                                            Total: <span className="text-accent-900">{events.length}</span> events
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

export default Events;

