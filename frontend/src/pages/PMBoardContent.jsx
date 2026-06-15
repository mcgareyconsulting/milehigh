/**
 * @milehigh-header
 * schema_version: 1
 * purpose: PM Board / Timeline content for the shared releases shell. Consumes the toolbar-filtered release set (boardJobs) from ReleasesLayout via Outlet context and renders either the Kanban list (PMBoardList) or the Gantt timeline (GanttChart) based on ?view=. The toolbar/header lives in ReleasesLayout — this is content only.
 * exports:
 *   PMBoardContent: Child route element for /pm-board; ?view=timeline → Gantt, otherwise list.
 * imports_from: [react, react-router-dom, ../components/PMBoardList, ../components/GanttChart]
 * imported_by: [../App.jsx]
 * invariants:
 *   - View mode derives from the URL (?view=timeline → Gantt, otherwise list), so the timeline is deep-linkable.
 *   - The list is narrowed by the toolbar filters (Projects / quick-filter subset / Search) via boardJobs; column-header filters do NOT apply here.
 *   - The Timeline (GanttChart) reads the full shared dataset itself and is intentionally unfiltered.
 */
import React from 'react';
import { useSearchParams, useOutletContext } from 'react-router-dom';
import PMBoardList from '../components/PMBoardList';
import GanttChart from '../components/GanttChart';

function PMBoardContent() {
    const { boardJobs, loading, fetchError, refetch } = useOutletContext();
    const [searchParams] = useSearchParams();
    const viewMode = searchParams.get('view') === 'timeline' ? 'timeline' : 'list';

    return (
        <div className="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-xl shadow-sm overflow-hidden flex-1 min-h-0 flex flex-col">
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
                viewMode === 'list' ? (
                    <PMBoardList
                        jobs={boardJobs}
                        onUpdate={() => refetch(true)}
                    />
                ) : (
                    <GanttChart filterComplete={true} />
                )
            )}
        </div>
    );
}

export default PMBoardContent;
