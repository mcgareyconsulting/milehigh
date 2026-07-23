/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for the K2 grid engine's per-user layout. Reads and writes one layout
 *   list per (user, surface) via /brain/layout/<surface_key> — per panel: id, size class and
 *   hidden flag. Both calls are best-effort: the grid keeps a localStorage copy and stays
 *   fully usable if the server is unreachable, so callers treat a rejected promise as "no
 *   server layout", not an error.
 * exports:
 *   fetchLayout(surfaceKey): Promise<Array>          saved layout ([] if none)
 *   saveLayout(surfaceKey, layout): Promise<Array>   persisted layout
 * imports_from: [axios, ../utils/api]
 * imported_by: [components/grid/useGridLayout.js]
 * invariants:
 *   - withCredentials sends the session cookie; the route is login-gated and scopes rows to
 *     the current user server-side.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;
const BASE = `${API_BASE_URL}/brain/layout`;

export async function fetchLayout(surfaceKey) {
  const { data } = await axios.get(`${BASE}/${encodeURIComponent(surfaceKey)}`);
  return Array.isArray(data?.layout) ? data.layout : [];
}

export async function saveLayout(surfaceKey, layout) {
  const { data } = await axios.put(`${BASE}/${encodeURIComponent(surfaceKey)}`, { layout });
  return Array.isArray(data?.layout) ? data.layout : layout;
}
