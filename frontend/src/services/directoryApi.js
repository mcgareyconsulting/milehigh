/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin HTTP calls for the user directory (employees + subcontractors)
 *          and employee permissions management.
 * exports:
 *   fetchDirectory: GET /brain/directory → {employees, subcontractors, roles}
 *   updateEmployeeRole: PATCH /brain/directory/employees/:id/role → updated employee row
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/UserDirectory.jsx]
 * invariants:
 *   - withCredentials sends the session cookie; both routes are admin-only server-side.
 *   - role is one of 'admin' | 'drafter' | 'default'; the server rejects anything else.
 *   - Subcontractors have no role endpoint — that group is unaffected by permissions.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

export async function fetchDirectory() {
    const { data } = await axios.get(`${API_BASE_URL}/brain/directory`);
    return data; // { employees, subcontractors, roles }
}

export async function updateEmployeeRole(userId, role) {
    const { data } = await axios.patch(
        `${API_BASE_URL}/brain/directory/employees/${userId}/role`,
        { role },
    );
    return data; // { id, first_name, last_name, email, role, role_key }
}
