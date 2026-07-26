/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for native T&M ticket creation — create/edit a draft ticket,
 *          list/inspect tickets, void a draft, and resolve release candidates for the picker.
 * exports:
 *   listTickets: List tickets, optionally filtered by status (draft|submitted|…|void).
 *   getTicket: Fetch one ticket plus its release_candidates.
 *   createTicket: Create a new draft ticket from form JSON.
 *   updateTicket: Persist edits to a draft ticket (PUT).
 *   voidTicket: Discard a ticket (kept as 'void', never deleted).
 *   getReleaseCandidates: Release options for a given job number, for the form's picker.
 *   ticketFileUrl: Streaming URL for a parked legacy upload's original document.
 *   listTicketAttachments/uploadTicketAttachment/deleteTicketAttachment: Photo/video
 *     field-evidence attachments (draft-only add/remove; always listable).
 *   ticketAttachmentFileUrl: Streaming URL for one attachment's bytes.
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/TMTickets.jsx, components/TMTicketFormModal.jsx, components/TMTicketAttachments.jsx]
 * invariants:
 *   - withCredentials sends the session cookie; admin-only mutations are enforced server-side.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;
const BASE = `${API_BASE_URL}/brain/tm-tickets`;

export async function listTickets(status) {
    const params = {};
    if (status) params.status = status;
    const { data } = await axios.get(BASE, { params });
    return data; // { tickets }
}

export async function getTicket(id) {
    const { data } = await axios.get(`${BASE}/${id}`);
    return data; // { ticket, release_candidates }
}

export async function createTicket(body) {
    const { data } = await axios.post(BASE, body);
    return data; // { ticket, release_candidates }
}

export async function updateTicket(id, body) {
    const { data } = await axios.put(`${BASE}/${id}`, body);
    return data; // { ticket }
}

export async function voidTicket(id) {
    const { data } = await axios.post(`${BASE}/${id}/void`);
    return data; // { ticket }
}

export async function getReleaseCandidates(job) {
    const { data } = await axios.get(`${BASE}/release-candidates`, { params: { job } });
    return data; // { candidates }
}

export function ticketFileUrl(id) {
    return `${BASE}/${id}/file`;
}

export async function listTicketAttachments(ticketId) {
    const { data } = await axios.get(`${BASE}/${ticketId}/attachments`);
    return data; // { tm_ticket_id, attachments }
}

export async function uploadTicketAttachment(ticketId, file) {
    const fd = new FormData();
    fd.append('file', file);
    const { data } = await axios.post(`${BASE}/${ticketId}/attachments`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data; // the attachment
}

export async function deleteTicketAttachment(ticketId, attachmentId) {
    const { data } = await axios.delete(`${BASE}/${ticketId}/attachments/${attachmentId}`);
    return data; // { status, attachment_id }
}

export function ticketAttachmentFileUrl(ticketId, attachmentId) {
    return `${BASE}/${ticketId}/attachments/${attachmentId}/file`;
}
