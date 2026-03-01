import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

/**
 * Search releases and submittals by 3-digit job number.
 * @param {string} job - Exactly 3 digits (e.g. '001', '400')
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
