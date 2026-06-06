/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared ASAP-set logic enforcing the 2-per-PM soft cap. Sets the ASAP flag and, when the
 *   backend returns 409 asap_limit, confirms with the user before retrying with force.
 * exports:
 *   setAsapWithCapConfirm(job, release): Promise<boolean> — true if the flag was set, false if the
 *     user declined past the cap. Throws on any other failure.
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
            if (!window.confirm(`${data.pm} already has ${data.count} ASAPs. Add anyway?`)) {
                return false;
            }
            await jobsApi.setStartInstallAsap(job, release, true, true);
            return true;
        }
        throw error;
    }
}
