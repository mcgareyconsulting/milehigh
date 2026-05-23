/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Displays a filterable audit trail of job and submittal events so admins can investigate what changed and when.
 * exports:
 *   Events: Page component rendering filter UI around the shared EventsList
 * imports_from: [react, react-router-dom, axios, ../utils/api, ../components/EventsList]
 * imported_by: [App.jsx]
 * invariants:
 *   - URL search params (submittal_id, job, release) pre-populate filters on mount and sync bidirectionally
 */
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import axios from 'axios';

import { API_BASE_URL } from '../utils/api';
import { EventsList } from '../components/EventsList';

function Events() {
    const [searchParams, setSearchParams] = useSearchParams();
    const [selectedDate, setSelectedDate] = useState('');
    const [availableDates, setAvailableDates] = useState([]);
    const [selectedSource, setSelectedSource] = useState('');
    const [availableSources, setAvailableSources] = useState([]);
    const [selectedUser, setSelectedUser] = useState('');
    const [availableUsers, setAvailableUsers] = useState([]);
    const [limit, setLimit] = useState(50);
    const [submittalId, setSubmittalId] = useState(searchParams.get('submittal_id') || '');
    const [jobFilter, setJobFilter] = useState(searchParams.get('job') || '');
    const [releaseFilter, setReleaseFilter] = useState(searchParams.get('release') || '');

    useEffect(() => {
        const urlSubmittalId = searchParams.get('submittal_id') || '';
        const urlJob = searchParams.get('job') || '';
        const urlRelease = searchParams.get('release') || '';
        setSubmittalId(urlSubmittalId);
        setJobFilter(urlJob);
        setReleaseFilter(urlRelease);
    }, [searchParams]);

    useEffect(() => {
        fetchFilters();
    }, []);

    const fetchFilters = async () => {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/events/filters`);
            const dates = [...new Set(
                response.data.dates
            )].sort().reverse();
            setAvailableDates(dates);
            const sources = response.data.sources;
            setAvailableSources(sources);
            setAvailableUsers(response.data.users || []);
        } catch (err) {
            console.error('Error fetching filters:', err);
        }
    };

    const resetFilters = () => {
        setSelectedDate('');
        setSelectedSource('');
        setSelectedUser('');
        setLimit(50);
        setSubmittalId('');
        setJobFilter('');
        setReleaseFilter('');
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
        <div className="w-full h-full flex flex-col bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900" style={{ width: '100%', minWidth: '100%' }}>
            <div className="flex-1 min-h-0 max-w-full mx-auto w-full py-2 px-2 flex flex-col" style={{ width: '100%' }}>
                <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl overflow-hidden flex flex-col flex-1 min-h-0">
                    {/* Title bar - matches DWL / Job Log */}
                    <div className="flex-shrink-0 px-4 py-3 bg-gradient-to-r from-accent-500 to-accent-600">
                        <div className="flex items-center justify-between">
                            <h1 className="text-3xl font-bold text-white">Job Events</h1>
                        </div>
                    </div>

                    <div className="p-2 flex flex-col flex-1 min-h-0 space-y-2">
                        <div className="bg-gradient-to-r from-gray-50 to-accent-50 dark:from-slate-700 dark:to-slate-700 rounded-xl p-3 border border-gray-200 dark:border-slate-600 shadow-sm flex-shrink-0">
                            <div className="flex flex-wrap gap-3 items-end">
                                <div className="flex-1 min-w-[200px]">
                                    <label className="block text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
                                        📅 Filter by Date
                                    </label>
                                    <select
                                        value={selectedDate}
                                        onChange={(e) => setSelectedDate(e.target.value)}
                                        className="w-full px-4 py-2.5 border border-gray-300 dark:border-slate-500 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white dark:bg-slate-600 dark:text-slate-100 shadow-sm transition-all"
                                    >
                                        <option value="">All Dates</option>
                                        {availableDates.map(date => (
                                            <option key={date} value={date}>{date}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="flex-1 min-w-[200px]">
                                    <label className="block text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
                                        🔗 Filter by Source
                                    </label>
                                    <select
                                        value={selectedSource}
                                        onChange={(e) => setSelectedSource(e.target.value)}
                                        className="w-full px-4 py-2.5 border border-gray-300 dark:border-slate-500 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white dark:bg-slate-600 dark:text-slate-100 shadow-sm transition-all"
                                    >
                                        <option value="">All Sources</option>
                                        {availableSources.map(source => (
                                            <option key={source} value={source}>{source}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="flex-1 min-w-[200px]">
                                    <label className="block text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
                                        👤 Filter by User
                                    </label>
                                    <select
                                        value={selectedUser}
                                        onChange={(e) => setSelectedUser(e.target.value)}
                                        className="w-full px-4 py-2.5 border border-gray-300 dark:border-slate-500 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white dark:bg-slate-600 dark:text-slate-100 shadow-sm transition-all"
                                    >
                                        <option value="">All Users</option>
                                        {availableUsers.map(user => (
                                            <option key={user.id} value={user.id}>{user.name}</option>
                                        ))}
                                    </select>
                                </div>
                                <div className="min-w-[150px]">
                                    <label className="block text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
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
                                                setLimit(50);
                                            } else {
                                                const parsed = parseInt(value, 10);
                                                if (!isNaN(parsed)) {
                                                    setLimit(Math.max(1, Math.min(200, parsed)));
                                                }
                                            }
                                        }}
                                        className="w-full px-4 py-2.5 border border-gray-300 dark:border-slate-500 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white dark:bg-slate-600 dark:text-slate-100 shadow-sm transition-all"
                                    />
                                </div>
                                <div className="flex items-end">
                                    <button
                                        onClick={resetFilters}
                                        className="px-6 py-2.5 bg-gray-200 dark:bg-slate-600 hover:bg-gray-300 dark:hover:bg-slate-500 text-gray-700 dark:text-slate-200 font-semibold rounded-lg text-sm transition-colors duration-150 shadow-sm hover:shadow border border-gray-300 dark:border-slate-500 flex items-center gap-2"
                                    >
                                        <span>🔄</span>
                                        Reset Filters
                                    </button>
                                </div>
                            </div>
                            {submittalId && (
                                <div className="mt-2 bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg px-3 py-2 flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <span className="text-blue-700 dark:text-blue-300 font-semibold">Filtered by Submittal ID:</span>
                                        <span className="text-blue-900 dark:text-blue-100 font-mono text-sm">{submittalId}</span>
                                    </div>
                                    <button
                                        onClick={clearSubmittalIdFilter}
                                        className="text-blue-700 dark:text-blue-300 hover:text-blue-900 dark:hover:text-blue-100 font-medium text-sm underline"
                                    >
                                        Clear
                                    </button>
                                </div>
                            )}
                            {(jobFilter || releaseFilter) && (
                                <div className="mt-2 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg px-3 py-2 flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <span className="text-green-700 dark:text-green-300 font-semibold">Filtered by Job:</span>
                                        <span className="text-green-900 dark:text-green-100 font-mono text-sm">
                                            {jobFilter}{releaseFilter ? `-${releaseFilter}` : ''}
                                        </span>
                                    </div>
                                    <button
                                        onClick={clearJobReleaseFilter}
                                        className="text-green-700 dark:text-green-300 hover:text-green-900 dark:hover:text-green-100 font-medium text-sm underline"
                                    >
                                        Clear
                                    </button>
                                </div>
                            )}
                        </div>

                        <EventsList
                            submittalId={submittalId}
                            jobFilter={jobFilter}
                            releaseFilter={releaseFilter}
                            selectedDate={selectedDate}
                            selectedSource={selectedSource}
                            selectedUser={selectedUser}
                            limit={limit}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Events;
