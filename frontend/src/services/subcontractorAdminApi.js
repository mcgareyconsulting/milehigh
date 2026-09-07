/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin HTTP calls for the subcontractor roster and T&M ticket assignment —
 *          invite/resend/deactivate/reactivate a subcontractor, and assign/unassign one
 *          to a specific ticket.
 * exports:
 *   listSubcontractors, getSubcontractor, inviteSubcontractor, resendInvite,
 *   deactivateSubcontractor, reactivateSubcontractor: Roster CRUD.
 *   listAssignableInstallerTeams, setInstallerTeam: Crew scoping — which installer crew's
 *     releases the account may see. Not /brain/installer-teams: that roster includes MHMW's
 *     own crews, which an external account must never be scoped to.
 *   listTicketSubcontractors, assignSubcontractor, unassignSubcontractor: Per-ticket assignment.
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/SubcontractorAdmin.jsx, components/TMTicketFormModal.jsx]
 * invariants:
 *   - withCredentials sends the session cookie; every route is admin-only server-side.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;
const ROSTER_BASE = `${API_BASE_URL}/brain/subcontractors`;
const TICKETS_BASE = `${API_BASE_URL}/brain/tm-tickets`;

export async function listSubcontractors() {
    const { data } = await axios.get(ROSTER_BASE);
    return data; // { subcontractors }
}

export async function getSubcontractor(id) {
    const { data } = await axios.get(`${ROSTER_BASE}/${id}`);
    return data; // the subcontractor
}

export async function inviteSubcontractor(body) {
    const { data } = await axios.post(ROSTER_BASE, body);
    return data; // the created subcontractor
}

export async function resendInvite(id) {
    const { data } = await axios.post(`${ROSTER_BASE}/${id}/resend-invite`);
    return data;
}

export async function deactivateSubcontractor(id) {
    const { data } = await axios.post(`${ROSTER_BASE}/${id}/deactivate`);
    return data;
}

export async function reactivateSubcontractor(id) {
    const { data } = await axios.post(`${ROSTER_BASE}/${id}/reactivate`);
    return data;
}

export async function listAssignableInstallerTeams() {
    const { data } = await axios.get(`${ROSTER_BASE}/installer-teams`);
    return data.installer_teams || [];
}

/** Pass null to clear the crew — that revokes release visibility without
 *  deactivating the account (the scope query fails closed on NULL). */
export async function setInstallerTeam(id, installerTeam) {
    const { data } = await axios.patch(`${ROSTER_BASE}/${id}/installer-team`, {
        installer_team: installerTeam,
    });
    return data; // the updated subcontractor
}

export async function listTicketSubcontractors(ticketId) {
    const { data } = await axios.get(`${TICKETS_BASE}/${ticketId}/subcontractors`);
    return data; // { subcontractors: [assignment, ...] }
}

export async function assignSubcontractor(ticketId, subcontractorId) {
    const { data } = await axios.post(`${TICKETS_BASE}/${ticketId}/subcontractors`, {
        subcontractor_id: subcontractorId,
    });
    return data; // the assignment
}

export async function unassignSubcontractor(ticketId, subcontractorId) {
    const { data } = await axios.delete(`${TICKETS_BASE}/${ticketId}/subcontractors/${subcontractorId}`);
    return data;
}
