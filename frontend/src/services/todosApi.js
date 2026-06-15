/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for the To-Do page (assigned checklist items).
 * exports:
 *   fetchTodos: List assigned to-dos (admin: all + filters; non-admin: own). Returns {todos, is_admin}.
 *   setTodoStatus: Mark a to-do done / reopen (owner or admin).
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/ToDos.jsx]
 * invariants:
 *   - withCredentials sends the session cookie; scoping is enforced server-side.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;
const BASE = `${API_BASE_URL}/brain`;

export async function fetchTodos({ status = 'open', owner } = {}) {
    const params = new URLSearchParams({ status });
    if (owner) params.set('owner', String(owner));
    const { data } = await axios.get(`${BASE}/todos?${params.toString()}`);
    return data; // { todos, is_admin }
}

export async function setTodoStatus(id, status) {
    const { data } = await axios.patch(`${BASE}/todos/${id}`, { status });
    return data; // updated checklist item
}
