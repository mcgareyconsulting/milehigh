/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for the Projects tab live rollups. Reads the Projects index and a
 *   single project's live payload (releases, submittals, merged activity, computed
 *   health) from the read-only /brain/projects endpoints. Financials/contract/customer
 *   have no backend source yet and are NOT returned here — the page overlays the live
 *   fields onto its demo scaffold for those sections.
 * exports:
 *   fetchProjectsIndex: list of projects + release/submittal counts + PM
 *   fetchProjectLive(jobNumber): live rollup payload for one project (404 -> null)
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/ProjectDetail.jsx]
 * invariants:
 *   - withCredentials sends the session cookie; read-only server-side.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;
const BASE = `${API_BASE_URL}/brain`;

export async function fetchProjectsIndex() {
  const { data } = await axios.get(`${BASE}/projects`);
  return data.projects; // [{job_number, name, pm, release_count, submittal_count, ...}]
}

export async function fetchProjectLive(jobNumber) {
  try {
    const { data } = await axios.get(`${BASE}/projects/${encodeURIComponent(jobNumber)}`);
    return data; // live rollup payload
  } catch (err) {
    if (err?.response?.status === 404) return null;
    throw err;
  }
}
