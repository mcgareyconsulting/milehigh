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

    // Compact toolbar controls, matching the Job Log filter chrome (CURRENT_STYLING_PIN §5).
    const selectClass = "px-2 py-0.5 text-xs border border-gray-300 dark:border-slate-500 rounded focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 bg-white dark:bg-slate-600 text-gray-900 dark:text-slate-100";
    const labelClass = "text-xs font-semibold text-gray-700 dark:text-slate-200 whitespace-nowrap";

    return (
        <div className="w-full h-full flex flex-col bg-canvas dark:bg-slate-900" style={{ width: '100%', minWidth: '100%' }}>
            <div className="flex-1 min-h-0 max-w-full mx-auto w-full flex flex-col" style={{ width: '100%' }}>
                {/* Subtle outer pad + gap between filter and table — no heavy white card (Job Log shell). */}
                <div className="bg-surface overflow-hidden flex flex-col flex-1 min-h-0 p-1.5 gap-1.5">
                    <div className="bg-gray-100 dark:bg-slate-700 p-1.5 rounded-md border border-gray-200/80 dark:border-slate-600 flex-shrink-0 space-y-1.5">
                        <div className="flex items-center gap-2 flex-wrap min-w-0">
                            <h1 className="text-sm font-bold text-ink whitespace-nowrap pr-1">Job Events</h1>
                            <div className="flex items-center gap-1.5">
                                <label className={labelClass}>Date:</label>
                                <select
                                    value={selectedDate}
                                    onChange={(e) => setSelectedDate(e.target.value)}
                                    className={selectClass}
                                >
                                    <option value="">All Dates</option>
                                    {availableDates.map(date => (
                                        <option key={date} value={date}>{date}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex items-center gap-1.5">
                                <label className={labelClass}>Source:</label>
                                <select
                                    value={selectedSource}
                                    onChange={(e) => setSelectedSource(e.target.value)}
                                    className={selectClass}
                                >
                                    <option value="">All Sources</option>
                                    {availableSources.map(source => (
                                        <option key={source} value={source}>{source}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex items-center gap-1.5">
                                <label className={labelClass}>User:</label>
                                <select
                                    value={selectedUser}
                                    onChange={(e) => setSelectedUser(e.target.value)}
                                    className={selectClass}
                                >
                                    <option value="">All Users</option>
                                    {availableUsers.map(user => (
                                        <option key={user.id} value={user.id}>{user.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="flex items-center gap-1.5">
                                <label className={labelClass}>Limit:</label>
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
                                    className={`${selectClass} w-16 font-mono`}
                                />
                            </div>
                            <button
                                onClick={resetFilters}
                                className="text-xs text-blue-600 dark:text-blue-400 underline hover:no-underline whitespace-nowrap"
                                title="Clear date, source, user, limit, and any submittal/job filters."
                            >
                                Reset
                            </button>
                        </div>
                        {(submittalId || jobFilter || releaseFilter) && (
                            <div className="flex items-center gap-1.5 flex-wrap border-t border-gray-200 dark:border-slate-600 pt-1.5">
                                <span className="text-xs font-semibold text-gray-500 dark:text-slate-400 whitespace-nowrap">Active filters:</span>
                                {submittalId && (
                                    <span className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 text-blue-700 dark:text-blue-300 text-xs font-medium">
                                        <span className="whitespace-nowrap">Submittal: <span className="font-mono">{submittalId}</span></span>
                                        <button
                                            type="button"
                                            onClick={clearSubmittalIdFilter}
                                            className="flex items-center justify-center w-4 h-4 rounded-full leading-none text-blue-500 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-800 hover:text-blue-800 dark:hover:text-blue-100 transition-colors"
                                            aria-label="Remove submittal filter"
                                            title="Remove submittal filter"
                                        >
                                            ×
                                        </button>
                                    </span>
                                )}
                                {(jobFilter || releaseFilter) && (
                                    <span className="inline-flex items-center gap-1 pl-2 pr-1 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 text-blue-700 dark:text-blue-300 text-xs font-medium">
                                        <span className="whitespace-nowrap">Job: <span className="font-mono">{jobFilter}{releaseFilter ? `-${releaseFilter}` : ''}</span></span>
                                        <button
                                            type="button"
                                            onClick={clearJobReleaseFilter}
                                            className="flex items-center justify-center w-4 h-4 rounded-full leading-none text-blue-500 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-800 hover:text-blue-800 dark:hover:text-blue-100 transition-colors"
                                            aria-label="Remove job filter"
                                            title="Remove job filter"
                                        >
                                            ×
                                        </button>
                                    </span>
                                )}
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
    );
}

export default Events;
