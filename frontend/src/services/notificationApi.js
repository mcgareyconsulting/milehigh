import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

const BASE = `${API_BASE_URL}/brain/notifications`;

export async function fetchNotifications() {
    const { data } = await axios.get(BASE);
    return data;
}

export async function fetchUnreadCount() {
    const { data } = await axios.get(`${BASE}/unread-count`);
    return data.unread_count;
}

export async function markNotificationRead(id) {
    const { data } = await axios.patch(`${BASE}/${id}/read`);
    return data;
}

export async function markAllRead() {
    const { data } = await axios.post(`${BASE}/read-all`);
    return data;
}
