/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for the subcontractor portal (T3) — the crew-scoped release feed, the
 *          phone Timeline envelope, one release's read-only detail, the sub's own to-dos and
 *          their mentions. Every endpoint is @subcontractor_login_required server-side.
 * exports:
 *   getSubReleases, getSubRelease, getSubDaySchedule,
 *   listSubTodos, setSubTodoStatus,
 *   listSubNotifications, subUnreadCount, markSubNotificationRead, markAllSubRead
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/SubcontractorJobLog.jsx, pages/SubcontractorTodos.jsx,
 *               components/SubcontractorShell.jsx, pages/SubcontractorRelease.jsx,
 *               components/sub/SubReleaseActivity.jsx, components/sub/SubReleaseAttachments.jsx]
 * invariants:
 *   - withCredentials sends the subcontractor session cookie; ALL scoping (crew, ownership,
 *     recipient) is enforced server-side — nothing here takes a crew or owner argument.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;
const BASE = `${API_BASE_URL}/brain/subcontractor`;

export async function getSubReleases() {
    const { data } = await axios.get(`${BASE}/releases`);
    return data; // { releases, installer_team }
}

/** Returns { release, stage_options } — the allowlisted row plus the stages a sub may set. */
/** The crew names this login resolves to (company crews, or the one admin-picked crew). */
export async function getSubCrews() {
    const { data } = await axios.get(`${BASE}/installer-teams`);
    return data.installer_teams || [];
}

export async function getSubRelease(id) {
    const { data } = await axios.get(`${BASE}/releases/${id}`);
    return data;
}

/** month = 'YYYY-MM' switches to that calendar month (every day, no past-due bucket);
 *  omitted = the rolling window (pastDays back, days forward, past-due triaged). */
export async function getSubDaySchedule({ days = 14, pastDays = 14, month = null } = {}) {
    const params = { days, past_days: pastDays };
    if (month) params.month = month;
    const { data } = await axios.get(`${BASE}/install-schedule/by-day`, { params });
    return data; // { window, summary, past_due, days }
}

export async function listSubTodos(status = 'open') {
    const { data } = await axios.get(`${BASE}/todos`, { params: { status } });
    return data.todos;
}

export async function setSubTodoStatus(id, status) {
    const { data } = await axios.patch(`${BASE}/todos/${id}`, { status });
    return data;
}

export async function listSubNotifications(limit = 50) {
    const { data } = await axios.get(`${BASE}/notifications`, { params: { limit } });
    return data; // { notifications, unread_count }
}

/** {unread_count, unread_todos, unread_mentions} — to-dos count while their assignment /
 *  deadline ping is unread; mentions while their row is. */
export async function subUnreadCount() {
    const { data } = await axios.get(`${BASE}/notifications/unread-count`);
    return data;
}

export const TODO_NOTIFICATION_TYPES = ['checklist_assigned', 'checklist_due'];
export const MENTION_NOTIFICATION_TYPES = ['mention'];

export async function markSubNotificationRead(id) {
    const { data } = await axios.patch(`${BASE}/notifications/${id}/read`);
    return data;
}

/** @param {{ types?: string[] }} [opts] narrows the sweep to those notification types. */
export async function markAllSubRead({ types } = {}) {
    const qs = types?.length ? `?types=${encodeURIComponent(types.join(','))}` : '';
    const { data } = await axios.post(`${BASE}/notifications/read-all${qs}`);
    return data;
}

// ---- Release page: activity, notes, attachments ----

export async function getSubActivity(releaseId, limit = 200) {
    const { data } = await axios.get(`${BASE}/releases/${releaseId}/activity`, { params: { limit } });
    return data.events; // rows in the shape buildTimeline() reads
}

export async function addSubNote(releaseId, notes) {
    const { data } = await axios.post(`${BASE}/releases/${releaseId}/notes`, { notes });
    return data; // { status, event_id, notes }
}

export async function getSubAttachments(releaseId) {
    const { data } = await axios.get(`${BASE}/releases/${releaseId}/attachments`);
    return data; // { release_id, drawings, photos }
}

/** Streams through the sub session cookie; sub-scoped, so no staff route is ever hit. */
export const subDrawingFileUrl = (releaseId, versionId) =>
    `${BASE}/releases/${releaseId}/drawing/versions/${versionId}/file`;
export const subPhotoFileUrl = (releaseId, photoId) =>
    `${BASE}/releases/${releaseId}/photos/${photoId}/file`;

/** `stage` tags the photo for the department photo gate (the gate's entry stage). */
export async function uploadSubPhoto(releaseId, file, { note = '', stage = null } = {}) {
    const form = new FormData();
    form.append('file', file, file.name || 'photo.jpg');
    if (note) form.append('note', note);
    if (stage) form.append('stage', stage);
    const { data } = await axios.post(`${BASE}/releases/${releaseId}/photos`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data; // the new photo row
}

/** Retag a photo already on the release so it can satisfy the department photo gate. */
export async function tagSubPhoto(releaseId, photoId, stage) {
    const { data } = await axios.patch(`${BASE}/releases/${releaseId}/photos/${photoId}`, { stage });
    return data;
}

/** stage must be one of the release payload's stage_options (SUB_STAGES server-side).
 *  gateExceptionNote is the written reason there is no handoff photo (T13 gate). */
export async function setSubStage(releaseId, stage, { gateExceptionNote = null } = {}) {
    const body = { stage };
    if (gateExceptionNote) body.gate_exception_note = gateExceptionNote;
    const { data } = await axios.patch(`${BASE}/releases/${releaseId}/stage`, body);
    return data; // { status, event_id, stage }
}

/** A PDF becomes the release's next drawing version; images go through uploadSubPhoto. */
export async function uploadSubFile(releaseId, file, note = '') {
    const form = new FormData();
    form.append('file', file, file.name || 'file.pdf');
    if (note) form.append('note', note);
    const { data } = await axios.post(`${BASE}/releases/${releaseId}/files`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data; // the new drawing version row
}
