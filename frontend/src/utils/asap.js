/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared ASAP-set logic enforcing the 2-per-PM hard cap. Sets the ASAP flag and, when the
 *   backend returns 409 asap_limit, informs the user the cap was hit.
 * exports:
 *   setAsapWithCapConfirm(job, release): Promise<boolean> — true if the flag was set, false if the
 *     PM is at the cap. Throws on any other failure.
 *   setAsapAndAssign(job, release, installer): Promise<boolean> — set ASAP, then (when an installer
 *     was picked) assign it installer-only so the mirror bar is seeded in the same action.
 * imports_from: [../services/jobsApi]
 * imported_by: [frontend/src/components/JobsTableRow.jsx, frontend/src/components/StartInstallEditor.jsx]
 */
import { jobsApi } from '../services/jobsApi';

export async function setAsapWithCapConfirm(job, release) {
    try {
        await jobsApi.setStartInstallAsap(job, release, true);
        return true;
    } catch (error) {
        const data = error.originalError?.response?.data;
        if (error.statusCode === 409 && data?.error === 'asap_limit') {
            window.alert(`${data.pm} already has ${data.count} ASAPs (limit ${data.limit}). Clear one before adding another.`);
            return false;
        }
        throw error;
    }
}

export async function setAsapAndAssign(job, release, installer) {
    const ok = await setAsapWithCapConfirm(job, release);
    // ASAP stamps the date; if an installer was also picked, assign it (installer-only, null
    // date) so the ASAP date is kept and the mirror bar is seeded in the same action.
    if (ok && installer !== undefined) {
        await jobsApi.updateStartInstall(job, release, null, installer);
    }
    return ok;
}
