/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Shared ASAP-set logic enforcing the 2-per-PM hard cap. Sets the ASAP flag and, when the
 *   backend returns 409 asap_limit, informs the user the cap was hit.
 * exports:
 *   setAsapWithCapConfirm(job, release): Promise<boolean> — true if the flag was set, false if the
 *     PM is at the cap. Throws on any other failure.
 *   setAsapAndAssign(job, release, installer, startInstall): Promise<boolean> — set the ASAP flag,
 *     then save the hard date the user typed (and the installer, when one was picked) in the same
 *     action. ASAP no longer stamps a date, so the date save is what actually schedules the row.
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

export async function setAsapAndAssign(job, release, installer, startInstall) {
    const ok = await setAsapWithCapConfirm(job, release);
    // The flag goes first because it is the call that can 409 on the per-PM cap — no point
    // writing a date onto a row that was refused. The modal will not set ASAP without a
    // date, so startInstall is always a real YYYY-MM-DD by the time we get here.
    if (ok) {
        await jobsApi.updateStartInstall(job, release, startInstall, installer);
    }
    return ok;
}
