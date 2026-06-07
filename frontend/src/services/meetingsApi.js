/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for the meeting → checklist → to-do/notify feature so UI stays transport-agnostic.
 * exports:
 *   createMeeting: Ingest a transcript and get back the meeting + proposed checklist.
 *   sendBot: Dispatch a Recall notetaker bot to a meeting URL (dispatch-only, no save).
 *   fetchMeetings: List recent meetings.
 *   fetchMeeting: One meeting with its checklist items + transcript.
 *   generateChecklist: On-demand extraction of a meeting's transcript into to-dos.
 *   reviewChecklistItem: Accept / reject / done / edit an item (owner + due date editable).
 *   fetchAssignableUsers: Active users for the owner dropdown.
 *   scanDue: Manually trigger the deadline-notification scan.
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/Meetings.jsx]
 * invariants:
 *   - axios.defaults.withCredentials sends the session cookie on every request.
 *   - All endpoints are under /brain (meetings + checklist-items).
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

const BASE = `${API_BASE_URL}/brain`;

export async function createMeeting({ title, meeting_type, transcript, project_number }) {
    const { data } = await axios.post(`${BASE}/meetings`, {
        title, meeting_type, transcript, project_number,
    });
    return data; // meeting + items
}

// Dispatch a Recall notetaker bot to a meeting URL. Dispatch-only for now —
// no meeting is saved; this just confirms the bot joins and webhooks fire.
export async function sendBot({ meeting_url, bot_name } = {}) {
    const { data } = await axios.post(`${BASE}/meetings/bots`, { meeting_url, bot_name });
    return data; // { bot_id, status }
}

export async function fetchMeetings() {
    const { data } = await axios.get(`${BASE}/meetings`);
    return data.meetings;
}

export async function fetchMeeting(id) {
    const { data } = await axios.get(`${BASE}/meetings/${id}`);
    return data; // meeting + items + transcript
}

// On-demand: mine a meeting's transcript into a proposed checklist.
export async function generateChecklist(id, { regenerate = false } = {}) {
    const { data } = await axios.post(`${BASE}/meetings/${id}/generate-checklist`, { regenerate });
    return data; // meeting + items
}

export async function reviewChecklistItem(itemId, { action, fields } = {}) {
    const { data } = await axios.patch(`${BASE}/checklist-items/${itemId}`, { action, fields });
    return data; // updated item
}

export async function fetchAssignableUsers() {
    const { data } = await axios.get(`${BASE}/meetings/assignable-users`);
    return data.users;
}

export async function scanDue() {
    const { data } = await axios.post(`${BASE}/checklist-items/scan-due`);
    return data.notified;
}
