/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Provides notification CRUD calls for the in-app @mention notification system so the bell component can fetch, read, and bulk-dismiss notifications.
 * exports:
 *   fetchNotifications: Retrieve all notifications for the current user.
 *   fetchUnreadCount: Get the unread notification count for the badge.
 *   markNotificationRead: Mark a single notification as read.
 *   markAllRead: Mark all notifications as read in one call.
 * imports_from: [axios, ../utils/api]
 * imported_by: [components/NotificationBell.jsx]
 * invariants:
 *   - All endpoints are prefixed with /brain/notifications.
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
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

export async function fetchMentionableUsers() {
    const { data } = await axios.get(`${API_BASE_URL}/brain/mentionable-users`);
    return data.users;
}
