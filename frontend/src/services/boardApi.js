/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Centralizes all HTTP calls to the Brain Board (bug/feature tracker) so UI components stay transport-agnostic.
 * exports:
 *   fetchBoardItems: Retrieve board items with optional status/category/priority/search filters.
 *   fetchBoardItem: Retrieve a single board item by ID.
 *   createBoardItem: Create a new board item.
 *   updateBoardItem: Patch an existing board item.
 *   reorderBoardItems: Persist drag-drop column ordering.
 *   deleteBoardItem: Delete a board item by ID.
 *   fetchMentionableUsers: List users available for @mention in comments.
 *   addComment: Post a comment on a board item.
 * imports_from: [axios, ../utils/api]
 * imported_by: [components/board/NewItemModal.jsx, components/board/BoardDetail.jsx, pages/Board.jsx]
 * invariants:
 *   - axios.defaults.withCredentials is set globally so session cookies are sent on every request.
 *   - All endpoints are prefixed with /brain/board.
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

const BASE = `${API_BASE_URL}/brain/board`;

export async function fetchBoardItems(filters = {}) {
    const params = {};
    if (filters.status) params.status = filters.status;
    if (filters.category) params.category = filters.category;
    if (filters.priority) params.priority = filters.priority;
    if (filters.search) params.search = filters.search;

    const { data } = await axios.get(`${BASE}/items`, { params });
    return data.items;
}

export async function fetchBoardItem(id) {
    const { data } = await axios.get(`${BASE}/items/${id}`);
    return data;
}

export async function createBoardItem(item) {
    const { data } = await axios.post(`${BASE}/items`, item);
    return data;
}

export async function updateBoardItem(id, updates) {
    const { data } = await axios.patch(`${BASE}/items/${id}`, updates);
    return data;
}

export async function reorderBoardItems(status, orderedIds) {
    const { data } = await axios.patch(`${BASE}/items/reorder`, {
        status,
        ordered_ids: orderedIds,
    });
    return data;
}

export async function deleteBoardItem(id) {
    await axios.delete(`${BASE}/items/${id}`);
}

export async function fetchMentionableUsers() {
    const { data } = await axios.get(`${BASE}/mentionable-users`);
    return data.users;
}

export async function addComment(itemId, body) {
    const { data } = await axios.post(`${BASE}/items/${itemId}/activity`, { body });
    return data;
}
