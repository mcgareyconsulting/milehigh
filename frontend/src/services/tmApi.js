/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for the T&M ticket ingestion feature — upload a scanned/photographed
 *          ticket, list/inspect extracted tickets, and confirm or reject the extraction.
 * exports:
 *   listTickets: List tickets, optionally filtered by status (pending_review|confirmed|rejected).
 *   getTicket: Fetch one ticket plus its release_candidates.
 *   uploadTicket: Multipart upload of the source document; kicks off AI extraction.
 *   confirmTicket: Persist reviewer-edited fields (and release link) on a ticket.
 *   rejectTicket: Mark a ticket rejected.
 *   getReleaseCandidates: Release options for a given job number, for the review modal's picker.
 *   ticketFileUrl: Build the streaming URL for a ticket's original document bytes.
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/TMTickets.jsx, components/TMReviewModal.jsx]
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

export async function uploadTicket(file) {
    const fd = new FormData();
    fd.append('file', file);
    const { data } = await axios.post(BASE, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data; // { ticket, release_candidates }
}

export async function confirmTicket(id, body) {
    const { data } = await axios.post(`${BASE}/${id}/confirm`, body);
    return data; // { ticket }
}

export async function rejectTicket(id) {
    const { data } = await axios.post(`${BASE}/${id}/reject`);
    return data; // { ticket }
}

export async function getReleaseCandidates(job) {
    const { data } = await axios.get(`${BASE}/release-candidates`, { params: { job } });
    return data; // { candidates }
}

export function ticketFileUrl(id) {
    return `${BASE}/${id}/file`;
}
