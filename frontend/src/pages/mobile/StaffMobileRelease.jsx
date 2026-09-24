/**
 * @milehigh-header
 * schema_version: 1
 * purpose: /m/releases/:id — the same phone release page subs get, over the staff routes, so the
 *          client can test one surface from either login. Staff get the full stage progression;
 *          photos and PDFs upload through the ordinary release routes.
 * exports:
 *   StaffMobileRelease: Page component under StaffMobileShell.
 * imports_from: [../../components/mobile/MobileReleasePage, ../../components/mobile/releaseApi]
 * imported_by: [App.jsx]
 */
import MobileReleasePage from '../../components/mobile/MobileReleasePage';
import { staffReleaseApi } from '../../components/mobile/releaseApi';

export default function StaffMobileRelease() {
    return <MobileReleasePage api={staffReleaseApi} homePath="/m/job-log" />;
}
