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
