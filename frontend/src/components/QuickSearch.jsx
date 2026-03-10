import React, { useState, useEffect, useCallback, useRef } from 'react';
import { searchByJob } from '../services/jobSearchApi';
import { JobSearchTable } from '../pages/JobSearch/JobSearchTable';
import { formatDateShort } from '../utils/formatters';

const DEBOUNCE_MS = 350;

const RELEASES_COLS = [
  { key: 'job_release', label: 'Job-Release', className: 'font-mono' },
  { key: 'job_name', label: 'Job Name', format: (v) => v != null ? (String(v).length > 15 ? String(v).slice(0, 15) + '…' : String(v)) : '—' },
  { key: 'stage', label: 'Stage' },
  { key: 'start_install', label: 'Start Install', format: (v) => formatDateShort(v) },
];
const SUBMITTALS_COLS = [
  { key: 'title', label: 'Title' },
  { key: 'status', label: 'Status' },
  { key: 'ball_in_court', label: 'BIC' },
  { key: 'submittal_drafting_status', label: 'Drafting Status' },
  { key: 'days_since_ball_in_court_update', label: 'Time Since Last BIC', format: (v) => (v != null ? `${v} days` : '—') },
];

export default function QuickSearch() {
  const [jobInput, setJobInput] = useState('');
  const [releases, setReleases] = useState([]);
  const [submittals, setSubmittals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchedJob, setSearchedJob] = useState(null);
  const debounceRef = useRef(null);
  const containerRef = useRef(null);

  const runSearch = useCallback(async (trimmed) => {
    if (!trimmed || !/^\d{1,3}$/.test(trimmed)) return;
    setError(null);
    setLoading(true);
    try {
      const data = await searchByJob(trimmed);
      setReleases(data.releases);
      setSubmittals(data.submittals);
      setSearchedJob(data.job);
    } catch (err) {
      const msg = err.response?.data?.error || err.message || 'Search failed';
      setError(msg);
      setReleases([]);
      setSubmittals([]);
      setSearchedJob(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const trimmed = jobInput.trim().replace(/\s/g, '');
    if (!trimmed) {
      setError(null);
      setReleases([]);
      setSubmittals([]);
      setSearchedJob(null);
      return;
    }
    if (!/^\d{1,3}$/.test(trimmed)) {
      setError('Enter 1–3 digits (e.g. 4, 40, 400)');
      return;
    }

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runSearch(trimmed), DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [jobInput, runSearch]);

  // Click-outside: clear input and close dropdown
  useEffect(() => {
    const handleMouseDown = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setJobInput('');
      }
    };
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, []);

  const isOpen = searchedJob != null || loading || !!error;

  return (
    <div ref={containerRef} className="relative">
      {/* Compact search input */}
      <div className="relative flex items-center">
        <span className="absolute left-3 text-accent-400" aria-hidden>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </span>
        <input
          id="quick-search-input"
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={3}
          placeholder="Project #"
          value={jobInput}
          onChange={(e) => setJobInput(e.target.value.replace(/\D/g, '').slice(0, 3))}
          className="w-36 pl-9 pr-3 py-1.5 bg-gray-100 dark:bg-slate-700 border border-gray-200 dark:border-slate-600 rounded-lg font-mono text-sm text-gray-900 dark:text-slate-100 placeholder-gray-500 dark:placeholder-slate-400 focus:bg-white dark:focus:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-accent-500 transition-colors"
        />
      </div>

      {/* Dropdown results panel */}
      {isOpen && (
        <div className="fixed left-4 right-4 mt-1 z-50 max-h-[45vh] overflow-y-auto bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-xl shadow-xl" style={{ top: '3.75rem' }}>
          {loading && (
            <p className="px-4 py-3 text-sm text-gray-500 dark:text-slate-400">Searching…</p>
          )}
          {error && (
            <p className="px-4 py-3 text-sm text-red-600 dark:text-red-400">{error}</p>
          )}
          {searchedJob != null && !error && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 p-4">
              <div className="flex flex-col">
                <h4 className="text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">Releases</h4>
                <JobSearchTable
                  columns={RELEASES_COLS}
                  rows={releases}
                  emptyMessage="No releases found"
                  jumpTo={{
                    label: 'Jump To',
                    getUrl: (row) => {
                      const job = row.job ?? row.job_release?.split?.('-')[0];
                      const release = row.release ?? row.job_release?.split?.('-').slice(1).join('-');
                      return (job != null && release != null && String(job) !== '' && String(release) !== '')
                        ? `/job-log?job=${job}&release=${encodeURIComponent(release)}`
                        : null;
                    },
                    onJump: () => setJobInput(''),
                  }}
                />
              </div>
              <div className="flex flex-col">
                <h4 className="text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">Submittals</h4>
                <JobSearchTable
                  columns={SUBMITTALS_COLS}
                  rows={submittals}
                  emptyMessage="No submittals found"
                  jumpTo={{
                    label: 'Jump To',
                    getUrl: (row) => {
                      const sid = row.submittal_id;
                      return (sid != null && sid !== '')
                        ? `/drafting-work-load?highlight=${encodeURIComponent(String(sid))}`
                        : null;
                    },
                    onJump: () => setJobInput(''),
                  }}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
