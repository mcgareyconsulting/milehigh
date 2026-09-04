/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Provides notification CRUD calls for the in-app @mention notification system so the bell component can fetch, read, and bulk-dismiss notifications.
 * exports:
 *   fetchNotifications: Retrieve notifications for the current user (optional type/limit narrowing).
 *   fetchUnreadCount: Get the unread notification count for the badge.
 *   markNotificationRead: Mark a single notification as read.
 *   markAllRead: Mark notifications read in one call (optionally only certain types).
 *   MENTION_TYPES: The notification types that represent an @mention.
 * imports_from: [axios, ../utils/api]
 * imported_by: [components/NotificationBell.jsx, pages/ToDos.jsx]
 * invariants:
 *   - All endpoints are prefixed with /brain/notifications.
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

const BASE = `${API_BASE_URL}/brain/notifications`;

/**
 * @param {{ types?: string[], limit?: number, owner?: string }} [opts]
 *   types narrows to specific notification types (e.g. ['mention', 'dwl_mention']),
 *   so a mentions-only view isn't crowded out of the shared row cap by to-dos.
 *   owner retargets the recipient — a user id, or 'all' for everyone. Admin-only
 *   server-side; a non-admin is always pinned to their own rows, and omitting it
 *   means "me", which is what the notification bell relies on.
 */
export async function fetchNotifications({ types, limit, owner } = {}) {
    const params = new URLSearchParams();
    if (types?.length) params.set('types', types.join(','));
    if (limit) params.set('limit', String(limit));
    if (owner) params.set('owner', String(owner));
    const qs = params.toString();
    const { data } = await axios.get(qs ? `${BASE}?${qs}` : BASE);
    return data;
}

/**
 * Notification types that mean "someone @mentioned you" — as opposed to a to-do
 * assignment or an agent report. Passed as ?types to scope a mentions-only view.
 */
export const MENTION_TYPES = ['mention', 'dwl_mention'];

export async function fetchUnreadCount() {
    const { data } = await axios.get(`${BASE}/unread-count`);
    return data.unread_count;
}

export async function markNotificationRead(id) {
    const { data } = await axios.patch(`${BASE}/${id}/read`);
    return data;
}

/** @param {{ types?: string[] }} [opts] narrows the sweep to those types only. */
export async function markAllRead({ types } = {}) {
    const qs = types?.length ? `?types=${encodeURIComponent(types.join(','))}` : '';
    const { data } = await axios.post(`${BASE}/read-all${qs}`);
    return data;
}

export async function fetchMentionableUsers() {
    const { data } = await axios.get(`${API_BASE_URL}/brain/mentionable-users`);
    return data.users;
}
