/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Timeline content for the shared releases shell — renders the Gantt timeline (GanttChart). The PM Board Kanban list was removed 2026-07-12 (company change); /pm-board now always shows the timeline, so old ?view=timeline deep links and bare /pm-board both land here. The toolbar/header lives in ReleasesLayout — this is content only.
 * exports:
 *   PMBoardContent: Child route element for /pm-board (Timeline view).
 * imports_from: [react, react-router-dom, ../components/GanttChart]
 * imported_by: [../App.jsx]
 * invariants:
 *   - The Timeline (GanttChart) reads the full shared dataset itself and is intentionally unfiltered.
 *   - Read-only view: edits happen in the Job Log (the timeline's drag interactions were removed with the Board).
 */
import React from 'react';
import { useOutletContext } from 'react-router-dom';
import GanttChart from '../components/GanttChart';

function PMBoardContent() {
    const { loading, fetchError } = useOutletContext();

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
                <GanttChart filterComplete={true} />
            )}
        </div>
    );
}

export default PMBoardContent;
