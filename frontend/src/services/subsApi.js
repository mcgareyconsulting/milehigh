/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for the admin Subs page (installer invoice paid tracking).
 * exports:
 *   fetchSubsReleases: List active assigned releases + distinct installers
 *   updateInstallerInvoicePaid: Toggle paid yes/no for a job-release
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/Subs.jsx]
 * invariants:
 *   - withCredentials sends the session cookie; admin is enforced server-side.
 *   - This is NOT the customer-billing `invoiced` field on the job log.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;
const BASE = `${API_BASE_URL}/brain/subs`;

export async function fetchSubsReleases({ paid, installer } = {}) {
    const params = new URLSearchParams();
    if (paid === true) params.set('paid', 'true');
    if (paid === false) params.set('paid', 'false');
    if (installer) params.set('installer', installer);
    const qs = params.toString();
    const { data } = await axios.get(`${BASE}/releases${qs ? `?${qs}` : ''}`);
    return data; // { releases, installers }
}

export async function updateInstallerInvoicePaid(job, release, installerInvoicePaid) {
    const { data } = await axios.patch(
        `${BASE}/releases/${job}/${encodeURIComponent(release)}/installer-invoice-paid`,
        { installer_invoice_paid: !!installerInvoicePaid },
    );
    return data;
}
