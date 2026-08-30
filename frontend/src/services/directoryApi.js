/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin HTTP call for the user directory (employees + subcontractors).
 * exports:
 *   fetchDirectory: GET /brain/directory → {employees, subcontractors}
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/UserDirectory.jsx]
 * invariants:
 *   - withCredentials sends the session cookie; the route is admin-only server-side.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

export async function fetchDirectory() {
    const { data } = await axios.get(`${API_BASE_URL}/brain/directory`);
    return data; // { employees, subcontractors }
}
