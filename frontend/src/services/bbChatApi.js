/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for the read-only BB (Banana Boy) chat assistant + its admin access toggle.
 * exports:
 *   sendMessage: POST a question; returns { conversation_id, user_message, assistant_message }.
 *   listConversations: List my chat threads (metadata).
 *   getConversation: One thread with its full message history.
 *   listAccessUsers: (admin) users + their is_bb_chat flag.
 *   setUserAccess: (admin) grant/revoke a user's BB-chat access.
 * imports_from: [axios, ../utils/api]
 * imported_by: [components/BBChatWidget.jsx]
 * invariants:
 *   - withCredentials sends the session cookie; access is enforced server-side by is_bb_chat.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;
const BASE = `${API_BASE_URL}/brain/bb-chat`;

export async function sendMessage(message, conversationId) {
    const { data } = await axios.post(BASE, {
        message,
        conversation_id: conversationId || undefined,
    });
    return data; // { conversation_id, user_message, assistant_message }
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
    return data.users; // [{ id, username, name, is_admin, is_bb_chat }]
}

export async function setUserAccess(userId, isBbChat) {
    const { data } = await axios.post(`${BASE}/admin/users/${userId}/access`, {
        is_bb_chat: isBbChat,
    });
    return data; // { id, is_bb_chat }
}
