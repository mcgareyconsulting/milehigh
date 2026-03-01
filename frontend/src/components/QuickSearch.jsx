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

  return (
    <div className="flex-1 flex flex-col min-h-0 w-full max-w-[1600px] mx-auto">
      <div className="bg-white/95 backdrop-blur-sm rounded-xl shadow-lg border border-gray-200 flex flex-col flex-1 min-h-0 overflow-hidden">
        <div className="flex-shrink-0 p-4 border-b border-gray-100">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <label htmlFor="quick-search-input" className="text-sm font-medium text-gray-700">
              Job number
            </label>
            <div className="flex items-center gap-3">
              <input
                id="quick-search-input"
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={3}
                placeholder="4 = 4xx • 40 = 40x • 400 = exact"
                value={jobInput}
                onChange={(e) => setJobInput(e.target.value.replace(/\D/g, '').slice(0, 3))}
                autoFocus
                className="flex-1 max-w-[12rem] px-4 py-3 border border-gray-200 rounded-xl font-mono text-xl bg-gray-50 text-gray-900 placeholder-gray-400 focus:bg-white focus:ring-2 focus:ring-accent-400 focus:border-accent-400"
              />
              {loading && (
                <span className="text-sm text-gray-500">Searching…</span>
              )}
            </div>
          </div>

          {error && (
            <p className="mt-2 text-sm text-red-600">{error}</p>
          )}
        </div>

        {searchedJob != null && !error ? (
          <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-2 gap-4 p-4 overflow-hidden">
            <div className="flex flex-col min-h-0">
              <h4 className="flex-shrink-0 text-sm font-semibold text-gray-700 mb-2">Releases</h4>
              <div className="flex-1 min-h-0 overflow-auto">
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
                  }}
                />
              </div>
            </div>
            <div className="flex flex-col min-h-0">
              <h4 className="flex-shrink-0 text-sm font-semibold text-gray-700 mb-2">Submittals</h4>
              <div className="flex-1 min-h-0 overflow-auto">
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
                  }}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center min-h-0 p-8">
            <div className="text-center">
              <img
                src="/logo.jpg"
                alt=""
                className="max-w-[min(40vw,280px)] w-auto h-auto object-contain opacity-25 mx-auto"
                aria-hidden
              />
              <p className="mt-4 text-sm text-gray-500">
                Type 1–3 digits to search (4 = 4xx, 40 = 40x, 400 = exact)
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
