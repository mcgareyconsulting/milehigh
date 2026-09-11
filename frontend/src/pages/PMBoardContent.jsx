/**
 * @milehigh-header
 * schema_version: 3
 * purpose: Timeline content for the shared releases shell. At a desk it renders the Gantt timeline (GanttChart). The PM Board Kanban list was removed 2026-07-12 (company change); /pm-board now always shows the timeline, so old ?view=timeline deep links and bare /pm-board both land here. The toolbar/header lives in ReleasesLayout — this is content only.
 * exports:
 *   PMBoardContent: Child route element for /pm-board (Timeline view).
 * imports_from: [react, react-router-dom, ../hooks/useBreakpoint, ../hooks/useDaySchedule,
 *   ../components/GanttChart, ../components/installSchedule/DaySchedule,
 *   ../components/installSchedule/CrewSelect, ../components/ReleaseHubModal]
 * imported_by: [../App.jsx]
 * invariants:
 *   - The Timeline (GanttChart) reads the full shared dataset itself and is intentionally unfiltered.
 *   - ON A PHONE THE TIMELINE IS THE VERTICAL DAY CALENDAR, rendered right here. GanttChart freezes
 *     392px of chrome left of its first date column (STAGING_PX 200 + SIDEBAR_PX 192), which is wider
 *     than a phone viewport — so on a handset every visible pixel is chrome and the grid is
 *     unreachable. Days-as-rows is the same releases in a shape that fits.
 *   - IT MUST NOT NAVIGATE AWAY. An earlier pass sent phones to /install-schedule with a link; that
 *     drops the reader out of the Job Log shell (losing the toolbar, the filters and the Table/
 *     Timeline switch) to read what is still the Timeline. The vertical column IS this view on a
 *     phone, not a pointer to a different page.
 *   - ONE control only: the installer picker. The shell's toolbar sits directly above, so a second
 *     band of filters is the thing that made the schedule page feel cramped — but which installer's
 *     work you are looking at is the question this view exists to answer, so that one earns its line.
 *     No range control and no stat line.
 *   - There is no orientation LOCK available — screen.orientation.lock() is unsupported in iOS
 *     Safari and the app ships no PWA manifest — so rotating is a request, never a guarantee. The
 *     calendar has to be genuinely usable in portrait rather than a nag to turn the phone.
 */
import React, { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { useBreakpoint } from '../hooks/useBreakpoint';
import { useDaySchedule, useReleaseHub } from '../hooks/useDaySchedule';
import GanttChart from '../components/GanttChart';
import DaySchedule from '../components/installSchedule/DaySchedule';
import CrewSelect from '../components/installSchedule/CrewSelect';
import { ReleaseHubModal } from '../components/ReleaseHubModal';

/** The phone Timeline: the same releases, stacked by day instead of spread across lanes. */
function TimelineCalendar() {
    const [installer, setInstaller] = useState(null);
    const { data, loading, error, reload, roster, crewOptions } = useDaySchedule({
        days: 14, pastDays: 14, installer,
    });
    const { hubJob, openRelease, closeHub } = useReleaseHub();

    return (
        <div className="flex-1 min-h-0 flex flex-col p-3 gap-2">
            <CrewSelect
                crews={crewOptions}
                value={installer}
                onChange={setInstaller}
                className="w-full max-w-[18rem]"
            />

            {loading && <div className="text-ink-3 text-sm">Loading timeline…</div>}
            {error && <div className="text-red-600 dark:text-red-400 text-sm">{error}</div>}
            {!loading && !error && (
                <DaySchedule data={data} roster={roster} onOpenRelease={openRelease} />
            )}

            {/* The SAME modal a Job Log row or the desktop Timeline opens. */}
            <ReleaseHubModal
                isOpen={!!hubJob}
                job={hubJob}
                releaseId={hubJob?.id}
                viewerUrl={hubJob?.viewer_url}
                initialTab="details"
                onClose={closeHub}
                onJobUpdate={reload}
            />
        </div>
    );
}

function PMBoardContent() {
    const { loading, fetchError } = useOutletContext();
    const { isMobile } = useBreakpoint();

    return (
        <div className="bg-surface border border-hairline rounded-xl shadow-sm overflow-hidden flex-1 min-h-0 flex flex-col">
            {loading && (
                <div className="text-center py-12">
                    <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                    <p className="text-gray-600 dark:text-slate-300 font-medium">Loading jobs data...</p>
                </div>
            )}

            {fetchError && !loading && (
                <div className="bg-red-50 dark:bg-red-900/30 border-l-4 border-red-500 text-red-700 dark:text-red-300 px-6 py-4 m-4">
                    <div className="flex items-start">
                        <span className="text-xl mr-3">⚠️</span>
                        <div>
                            <p className="font-semibold">Unable to load jobs data</p>
                            <p className="text-sm mt-1">{fetchError}</p>
                        </div>
                    </div>
                </div>
            )}

            {!loading && !fetchError && (
                isMobile ? <TimelineCalendar /> : <GanttChart filterComplete={true} />
            )}
        </div>
    );
}

export default PMBoardContent;
