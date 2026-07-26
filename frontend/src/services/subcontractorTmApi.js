/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for the subcontractor-facing T&M ticket view — list/view/edit/submit
 *          tickets assigned to the logged-in subcontractor, and view (not upload) attachments.
 *          Mirrors services/tmApi.js's shape but hits /brain/subcontractor/tm-tickets/... and
 *          requires a Subcontractor session, not an admin one.
 * exports:
 *   listAssignedTickets, getAssignedTicket, updateAssignedTicket, submitAssignedTicket,
 *   listAssignedTicketAttachments, assignedTicketAttachmentFileUrl.
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/SubcontractorTicketList.jsx, pages/SubcontractorTicketDetail.jsx]
 * invariants:
 *   - withCredentials sends the subcontractor session cookie; scoping to "own assigned
 *     tickets only" is enforced server-side, not here.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;
const BASE = `${API_BASE_URL}/brain/subcontractor/tm-tickets`;

export async function listAssignedTickets() {
    const { data } = await axios.get(BASE);
    return data; // { tickets }
}

export async function getAssignedTicket(id) {
    const { data } = await axios.get(`${BASE}/${id}`);
    return data; // { ticket }
}

export async function updateAssignedTicket(id, body) {
    const { data } = await axios.put(`${BASE}/${id}`, body);
    return data; // { ticket }
}

export async function submitAssignedTicket(id) {
    const { data } = await axios.post(`${BASE}/${id}/submit`);
    return data; // { ticket }
}

export async function listAssignedTicketAttachments(id) {
    const { data } = await axios.get(`${BASE}/${id}/attachments`);
    return data; // { attachments }
}

export function assignedTicketAttachmentFileUrl(ticketId, attachmentId) {
    return `${BASE}/${ticketId}/attachments/${attachmentId}/file`;
}
