/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Project-manager board offering list and Gantt-timeline views of active jobs for high-level scheduling oversight.
 * exports:
 *   PMBoard: Page component toggling between PMBoardList and GanttChart views of job data
 * imports_from: [react, react-router-dom, ../hooks/useJobsDataFetching, ../components/PMBoardList, ../components/GanttChart]
 * imported_by: [App.jsx]
 * invariants:
 *   - View mode toggles between 'list' and 'timeline' without re-fetching data
 * updated_by_agent: 2026-05-04T00:00:00Z (Job-Log style chrome)
 */
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useJobsDataFetching } from '../hooks/useJobsDataFetching';
import PMBoardList from '../components/PMBoardList';
import GanttChart from '../components/GanttChart';

function PMBoard() {
    const navigate = useNavigate();
    const { jobs, loading, error: fetchError, refetch } = useJobsDataFetching();
    const [viewMode, setViewMode] = useState('list');

    const pillBase = 'px-2.5 py-1 rounded text-xs font-semibold transition-all whitespace-nowrap';
    const pillActive = `${pillBase} bg-blue-700 text-white`;
    const pillInactive = `${pillBase} bg-white dark:bg-slate-600 border border-gray-400 dark:border-slate-500 text-gray-700 dark:text-slate-200 hover:bg-gray-50 dark:hover:bg-slate-500`;

    return (
        <div className="w-full h-[calc(100vh-3.5rem)] bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 dark:from-slate-900 dark:via-slate-800 dark:to-slate-900 py-2 px-2 flex flex-col" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-full mx-auto w-full h-full flex flex-col" style={{ width: '100%' }}>
                <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl overflow-hidden flex flex-col h-full">
                    <div className="p-2 flex flex-col flex-1 min-h-0 space-y-1.5">
                        <div className="bg-gray-100 dark:bg-slate-700 rounded-lg p-1.5 border border-gray-200 dark:border-slate-600 flex-shrink-0">
                            <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-sm font-bold text-gray-700 dark:text-slate-200 mr-1">PM Board</span>
                                <button
                                    onClick={() => setViewMode('list')}
                                    className={viewMode === 'list' ? pillActive : pillInactive}
                                >
                                    List
                                </button>
                                <button
                                    onClick={() => setViewMode('timeline')}
                                    className={viewMode === 'timeline' ? pillActive : pillInactive}
                                >
                                    Timeline
                                </button>
                                <div className="flex-1" />
                                <button
                                    onClick={() => navigate('/job-log')}
                                    className={pillInactive}
                                >
                                    📋 Job Log
                                </button>
                            </div>
                        </div>

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
                                        jobs={jobs}
                                        onUpdate={() => refetch(true)}
                                    />
                                ) : (
                                    <GanttChart filterComplete={true} />
                                )
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default PMBoard;
