/**
 * @milehigh-header
 * schema_version: 3
 * purpose: /sub/releases/:id — the shared phone release page over the sub-scoped adapter.
 * exports:
 *   SubcontractorRelease: Page component, rendered inside SubcontractorShell's Outlet.
 * imports_from: [../components/mobile/MobileReleasePage, ../components/mobile/releaseApi]
 * imported_by: [App.jsx]
 */
import MobileReleasePage from '../components/mobile/MobileReleasePage';
import { subReleaseApi } from '../components/mobile/releaseApi';

export default function SubcontractorRelease() {
    return <MobileReleasePage api={subReleaseApi} homePath="/sub/job-log" />;
}
