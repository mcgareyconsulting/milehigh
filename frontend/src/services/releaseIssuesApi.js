/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for the Release Issue & Error Register (roadmap T11) — per-release
 *          issues with comments (@mentions), photo/PDF attachments and change history.
 * exports:
 *   fetchIssueOptions: Departments / categories / priorities / statuses (server-owned lists)
 *   listReleaseIssues: Issues on a release plus { open_count, open_estimated_cost } summary
 *   createReleaseIssue: Create an issue; returns the full detail payload
 *   getReleaseIssue: Issue + comments + attachments + changes
 *   updateReleaseIssue: Partial edit (PATCH); returns the refreshed detail payload
 *   addIssueComment: Post a comment (mentions parsed server-side)
 *   uploadIssueAttachment: Upload one photo/PDF, optionally tied to a comment
 *   deleteIssueAttachment: Soft delete an attachment
 *   issueAttachmentFileUrl: Streaming URL for one attachment's bytes
 * imports_from: [axios, ../utils/api, ../utils/imageCompress]
 * imported_by: [components/releaseIssues/ReleaseIssuesPane.jsx]
 * invariants:
 *   - withCredentials sends the session cookie; every route is admin-only server-side.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';
import { compressImage } from '../utils/imageCompress';

axios.defaults.withCredentials = true;
const BASE = `${API_BASE_URL}/brain`;

export async function fetchIssueOptions() {
    const { data } = await axios.get(`${BASE}/release-issues/options`);
    return data;
}

export async function listReleaseIssues(releaseId) {
    const { data } = await axios.get(`${BASE}/releases/${releaseId}/issues`);
    return data; // { release_id, issues, summary }
}

export async function createReleaseIssue(releaseId, payload) {
    const { data } = await axios.post(`${BASE}/releases/${releaseId}/issues`, payload);
    return data; // { issue, comments, attachments, changes }
}

export async function getReleaseIssue(issueId) {
    const { data } = await axios.get(`${BASE}/release-issues/${issueId}`);
    return data;
}

export async function updateReleaseIssue(issueId, patch) {
    const { data } = await axios.patch(`${BASE}/release-issues/${issueId}`, patch);
    return data;
}

export async function addIssueComment(issueId, body) {
    const { data } = await axios.post(`${BASE}/release-issues/${issueId}/comments`, { body });
    return data;
}

export async function uploadIssueAttachment(issueId, file, commentId = null) {
    // PDFs go up as-is; photos get the same client-side compression as other uploads.
    const isPdf = file.type === 'application/pdf' || /\.pdf$/i.test(file.name || '');
    const toSend = isPdf ? file : await compressImage(file);
    const form = new FormData();
    form.append('file', toSend, file.name);
    if (commentId != null) form.append('comment_id', String(commentId));
    const { data } = await axios.post(`${BASE}/release-issues/${issueId}/attachments`, form);
    return data;
}

export async function deleteIssueAttachment(issueId, attachmentId) {
    const { data } = await axios.delete(`${BASE}/release-issues/${issueId}/attachments/${attachmentId}`);
    return data;
}

export function issueAttachmentFileUrl(issueId, attachmentId) {
    return `${BASE}/release-issues/${issueId}/attachments/${attachmentId}/file`;
}
