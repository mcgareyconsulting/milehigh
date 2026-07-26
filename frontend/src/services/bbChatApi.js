/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for the read-only Carmen Miranda chat assistant + its admin access toggle.
 * exports:
 *   sendMessage: POST a question; returns { conversation_id, user_message, assistant_message }.
 *   listConversations: List my chat threads (metadata).
 *   getConversation: One thread with its full message history.
 *   listAccessUsers: (admin) users + their is_carmen_chat flag.
 *   setUserAccess: (admin) grant/revoke a user's Carmen-chat access.
 *   fetchLookaheadPdfBlob: session-authenticated GET of a look-ahead PDF artifact path.
 * imports_from: [axios, ../utils/api]
 * imported_by: [components/BBChatWidget.jsx, components/carmen/LookaheadPdfCard.jsx]
 * invariants:
 *   - withCredentials sends the session cookie; access is enforced server-side by is_carmen_chat.
 *   - Look-ahead PDF paths are always under /brain/lookahead/artifacts/ (never open as bare href).
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;
const BASE = `${API_BASE_URL}/brain/carmen-chat`;

export async function sendMessage(message, conversationId) {
    const { data } = await axios.post(BASE, {
        message,
        conversation_id: conversationId || undefined,
    });
    return data; // { conversation_id, user_message, assistant_message }
}

/**
 * Fetch a look-ahead PDF as a Blob with session credentials.
 * @param {string} downloadPath e.g. /brain/lookahead/artifacts/<id>.pdf
 */
export async function fetchLookaheadPdfBlob(downloadPath) {
    if (!downloadPath || typeof downloadPath !== 'string') {
        throw new Error('Missing download path');
    }
    // Only allow look-ahead artifact paths — never open arbitrary server paths from chat.
    if (!downloadPath.startsWith('/brain/lookahead/artifacts/') || downloadPath.includes('..')) {
        throw new Error('Invalid look-ahead PDF path');
    }
    const { data } = await axios.get(`${API_BASE_URL}${downloadPath}`, {
        responseType: 'blob',
        withCredentials: true,
    });
    return data;
}

export async function listConversations() {
    const { data } = await axios.get(`${BASE}/conversations`);
    return data.conversations; // [{ id, title, created_at, updated_at }]
}

export async function getConversation(id) {
    const { data } = await axios.get(`${BASE}/conversations/${id}`);
    return data; // { id, ..., messages: [...] }
}

export async function listAccessUsers() {
    const { data } = await axios.get(`${BASE}/admin/users`);
    return data.users; // [{ id, username, name, is_admin, is_carmen_chat }]
}

export async function setUserAccess(userId, isBbChat) {
    const { data } = await axios.post(`${BASE}/admin/users/${userId}/access`, {
        is_carmen_chat: isBbChat,
    });
    return data; // { id, is_carmen_chat }
}
