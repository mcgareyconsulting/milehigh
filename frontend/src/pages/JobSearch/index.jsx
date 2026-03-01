import React, { useState, useCallback } from 'react';
import { JobSearchTable } from './JobSearchTable';
import { searchByJob } from '../../services/jobSearchApi';
import {
  RELEASES_COLS,
  SUBMITTALS_COLS,
  isValidJobInput,
  getReleaseJumpUrl,
  getSubmittalJumpUrl,
} from './constants';

export default function JobSearch() {
  const [jobInput, setJobInput] = useState('');
  const [releases, setReleases] = useState([]);
  const [submittals, setSubmittals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchedJob, setSearchedJob] = useState(null);

  const handleSearch = useCallback(async () => {
    const trimmed = jobInput.trim();
    if (!isValidJobInput(trimmed)) {
      setError('Enter exactly 3 digits (e.g. 001, 400)');
      return;
    }

    setError(null);
    setLoading(true);
    try {
      const data = await searchByJob(trimmed);
      setReleases(data.releases);
      setSubmittals(data.submittals);
      setSearchedJob(data.job);
    } catch (err) {
      setError(err.response?.data?.error || err.message || 'Search failed');
      setReleases([]);
      setSubmittals([]);
      setSearchedJob(null);
    } finally {
      setLoading(false);
    }
  }, [jobInput]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSearch();
  };

  const handleInputChange = (e) => {
    setJobInput(e.target.value.replace(/\D/g, '').slice(0, 3));
  };

  return (
    <div
      className="w-full h-full flex flex-col bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50"
      style={{ width: '100%', minWidth: '100%' }}
    >
      <div className="flex-1 min-h-0 max-w-full mx-auto w-full py-2 px-2 flex flex-col" style={{ width: '100%' }}>
        <div className="bg-white rounded-2xl shadow-xl overflow-hidden flex flex-col flex-1 min-h-0">
          <header className="flex-shrink-0 px-4 py-3 bg-gradient-to-r from-accent-500 to-accent-600">
            <div className="flex items-center justify-between">
              <h1 className="text-3xl font-bold text-white">Job Search</h1>
              <div className="flex items-center gap-3">
                <label htmlFor="job-search-input" className="text-sm font-medium text-white/90">
                  Job number (3 digits)
                </label>
                <input
                  id="job-search-input"
                  type="text"
                  inputMode="numeric"
                  maxLength={3}
                  placeholder="e.g. 400"
                  value={jobInput}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  className="w-24 px-3 py-2 border border-gray-200 rounded-lg font-mono text-lg no-spin bg-white text-gray-900 placeholder-gray-400 focus:ring-2 focus:ring-accent-400 focus:border-accent-400"
                />
                <button
                  type="button"
                  onClick={handleSearch}
                  disabled={loading}
                  className="px-4 py-2 bg-white text-accent-600 font-medium rounded-lg hover:bg-accent-50 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm transition-all"
                >
                  {loading ? 'Searching…' : 'Search'}
                </button>
              </div>
            </div>
          </header>

          <div className="flex-1 min-h-0 p-4 flex flex-col overflow-hidden">
            {error && (
              <div className="flex-shrink-0 mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
                <p className="text-sm text-red-700">{error}</p>
              </div>
            )}

            {searchedJob != null && !error && (
              <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-2 gap-4 overflow-hidden">
                <section className="flex flex-col min-h-0">
                  <h2 className="flex-shrink-0 text-sm font-semibold text-gray-700 mb-2">
                    Releases (Job {searchedJob})
                  </h2>
                  <div className="flex-1 min-h-0 overflow-hidden">
                    <JobSearchTable
                      columns={RELEASES_COLS}
                      rows={releases}
                      emptyMessage="No releases found for this job."
                      jumpTo={{ getUrl: getReleaseJumpUrl }}
                    />
                  </div>
                </section>
                <section className="flex flex-col min-h-0">
                  <h2 className="flex-shrink-0 text-sm font-semibold text-gray-700 mb-2">
                    Submittals (Job {searchedJob})
                  </h2>
                  <div className="flex-1 min-h-0 overflow-hidden">
                    <JobSearchTable
                      columns={SUBMITTALS_COLS}
                      rows={submittals}
                      emptyMessage="No submittals found for this job."
                      jumpTo={{ getUrl: getSubmittalJumpUrl }}
                    />
                  </div>
                </section>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
