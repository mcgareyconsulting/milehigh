/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Builds the Gantt/Timeline project structure on the frontend from the shared releases dataset, replacing the deprecated /brain/gantt-data endpoint.
 * exports:
 *   buildGanttProjects: Pure selector — turns release row objects into projects[] (grouped by Job #, min/max dates, color palette) mirroring the old gantt-data route
 *   useGanttProjects: useMemo wrapper over useReleases().jobs
 * imports_from: [react, ../context/ReleasesContext]
 * imported_by: [../components/GanttChart.jsx]
 * invariants:
 *   - Eligibility mirrors the /gantt-data SQL filter: a hard Start install, finite Install HRS > 0, Stage Group in {FABRICATION, READY_TO_SHIP, COMPLETE}
 *   - filterComplete drops rows whose Stage === 'Complete' BEFORE grouping (same semantics the old GanttChart fetch applied)
 *   - Bar end date is comp_eta_effective (already floored to start_install server-side); never recomputed here
 *   - Color palette is the same 12-color cyclic list as the backend route, assigned by sorted-project index
 */
import { useMemo } from 'react';
import { useReleases } from '../context/ReleasesContext';

// Same 12-color palette as the /gantt-data route (routes.py), assigned by
// sorted-project index so colors are deterministic across reloads.
const COLORS = [
    '#3B82F6',  // blue
    '#10B981',  // green
    '#F59E0B',  // amber
    '#EF4444',  // red
    '#8B5CF6',  // purple
    '#EC4899',  // pink
    '#06B6D4',  // cyan
    '#F97316',  // orange
    '#84CC16',  // lime
    '#6366F1',  // indigo
    '#14B8A6',  // teal
    '#F43F5E',  // rose
];

const ELIGIBLE_STAGE_GROUPS = new Set(['FABRICATION', 'READY_TO_SHIP', 'COMPLETE']);

/**
 * Build the projects[] structure consumed by GanttChart from release rows.
 *
 * Replicates the /brain/gantt-data route over frontend row objects:
 *  - eligibility: Start install truthy, start_install_formulaTF !== true (hard date;
 *    null/false both count as hard), finite Install HRS > 0,
 *    Stage Group in {FABRICATION, READY_TO_SHIP, COMPLETE}
 *  - filterComplete: drop rows whose Stage === 'Complete' before grouping
 *  - bar end date: comp_eta_effective (already floored server-side; falls back to
 *    Start install if missing so every eligible release still has a visible bar)
 *  - group by Job #, project start/end = min/max release dates
 *  - releases sorted by startDate; projects sorted by startDate; cyclic color palette
 */
export function buildGanttProjects(jobs, { filterComplete = false } = {}) {
    const projectsDict = new Map();

    (jobs || []).forEach((job) => {
        // filterComplete drops fully-complete releases pre-grouping.
        if (filterComplete && job['Stage'] === 'Complete') {
            return;
        }

        const startInstall = job['Start install'];
        if (!startInstall) return;

        // Hard date only: formulaTF === true means a soft/formula projection.
        if (job['start_install_formulaTF'] === true) return;

        const installHrs = Number(job['Install HRS']);
        if (!Number.isFinite(installHrs) || installHrs <= 0) return;

        if (!ELIGIBLE_STAGE_GROUPS.has(job['Stage Group'])) return;

        // Bar end is the server-computed effective comp ETA. Floor at start so a
        // release with no usable end still renders a (1-day) bar.
        const endDate = job['comp_eta_effective'] || startInstall;

        const projectKey = job['Job #'];
        if (!projectsDict.has(projectKey)) {
            projectsDict.set(projectKey, {
                releases: [],
                startDates: [],
                endDates: [],
            });
        }
        const bucket = projectsDict.get(projectKey);

        bucket.releases.push({
            job: job['Job #'],
            release: job['Release #'],
            jobName: job['Job'],
            description: job['Description'] || '',
            startDate: startInstall,
            endDate,
            pm: job['PM'] || '',
            by: job['BY'] || '',
        });
        bucket.startDates.push(startInstall);
        bucket.endDates.push(endDate);
    });

    // Sort project keys the way the backend does (sorted(projects_dict.items()))
    // so the color index is stable.
    const sortedKeys = Array.from(projectsDict.keys()).sort((a, b) => {
        if (a < b) return -1;
        if (a > b) return 1;
        return 0;
    });

    const projects = sortedKeys.map((projectKey, idx) => {
        const data = projectsDict.get(projectKey);
        const firstRelease = data.releases[0];
        const projectStart = data.startDates.reduce((min, d) => (d < min ? d : min));
        const projectEnd = data.endDates.reduce((max, d) => (d > max ? d : max));

        const sortedReleases = [...data.releases].sort((a, b) =>
            (a.startDate || '') < (b.startDate || '') ? -1
                : (a.startDate || '') > (b.startDate || '') ? 1 : 0
        );

        return {
            project: projectKey,
            projectName: firstRelease.jobName,
            startDate: projectStart || null,
            endDate: projectEnd || null,
            releases: sortedReleases,
            color: COLORS[idx % COLORS.length],
        };
    });

    // Sort projects by start date
    projects.sort((a, b) =>
        (a.startDate || '') < (b.startDate || '') ? -1
            : (a.startDate || '') > (b.startDate || '') ? 1 : 0
    );

    return projects;
}

export function useGanttProjects({ filterComplete = false } = {}) {
    const { jobs, loading, error } = useReleases();
    const projects = useMemo(
        () => buildGanttProjects(jobs, { filterComplete }),
        [jobs, filterComplete]
    );
    return { projects, loading, error };
}
