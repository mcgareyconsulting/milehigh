/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Session-based auth helpers for the subcontractor-facing app — a separate identity
 *          from utils/auth.js's checkAuth/logout (internal staff). Never share state with the
 *          internal auth check; a subcontractor session and a staff session are mutually
 *          exclusive by design (see app/subcontractor_auth/ on the backend).
 * exports:
 *   checkSubcontractorAuth: Calls /api/subcontractor-auth/me and returns the subcontractor or null.
 *   subcontractorLogout: POSTs to /api/subcontractor-auth/logout to end the session.
 * imports_from: [../utils/api]
 * imported_by: [components/SubcontractorShell.jsx, pages/SubcontractorTicketList.jsx, pages/SubcontractorTicketDetail.jsx]
 * invariants:
 *   - Both functions swallow network errors and never throw, mirroring utils/auth.js.
 */
import { API_BASE_URL } from './api';

export const checkSubcontractorAuth = async () => {
    try {
        const response = await fetch(`${API_BASE_URL}/api/subcontractor-auth/me`, {
            credentials: 'include',
        });
        if (response.ok) {
            return await response.json();
        }
        return null;
    } catch {
        return null;
    }
};

export const subcontractorLogout = async () => {
    try {
        await fetch(`${API_BASE_URL}/api/subcontractor-auth/logout`, {
            method: 'POST',
            credentials: 'include',
        });
    } catch (err) {
        console.error('Subcontractor logout error:', err);
    }
};
