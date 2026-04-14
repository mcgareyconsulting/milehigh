/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Enables quick lookup of releases and submittals by job number prefix so users can find data across both systems in one call.
 * exports:
 *   searchByJob: Search releases and submittals by 1-3 digit job number prefix.
 * imports_from: [axios, ../utils/api]
 * imported_by: [components/QuickSearch.jsx, pages/JobSearch/index.jsx]
 * invariants:
 *   - Input is trimmed before sending; the API expects 1-3 digit strings.
 *   - Returns empty arrays (not undefined) for releases/submittals via nullish coalescing.
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

/**
 * Search releases and submittals by job number prefix (1–3 digits).
 * @param {string} job - 1–3 digits (e.g. '4' for 4xx, '40' for 40x, '400' exact)
 * @returns {Promise<{releases: Array, submittals: Array, job: string}>}
 * @throws Re-throws axios errors; err.response.data.error contains API error message
 */
export async function searchByJob(job) {
  const res = await axios.get(`${API_BASE_URL}/brain/job-search`, {
    params: { job: job.trim() },
  });
  return {
    releases: res.data.releases ?? [],
    submittals: res.data.submittals ?? [],
    job: res.data.job ?? job,
  };
}
