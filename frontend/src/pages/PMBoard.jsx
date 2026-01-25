import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useJobsDataFetching } from '../hooks/useJobsDataFetching';
import { jobsApi } from '../services/jobsApi';
import PMBoardList from '../components/PMBoardList';
import GanttChart from '../components/GanttChart';

function PMBoard() {
    const navigate = useNavigate();
    const { jobs, loading, error: fetchError, refetch } = useJobsDataFetching();
    const [viewMode, setViewMode] = useState('list'); // 'list' or 'timeline'

    return (
        <div className="w-full h-screen bg-gradient-to-br from-slate-50 via-accent-50 to-blue-50 py-2 px-2 flex flex-col" style={{ width: '100%', minWidth: '100%' }}>
            <div className="max-w-full mx-auto w-full h-full flex flex-col" style={{ width: '100%' }}>
                <div className="bg-white rounded-2xl shadow-xl overflow-hidden flex flex-col h-full">
                    <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-4 py-3 flex-shrink-0">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <h1 className="text-3xl font-bold text-white">PM Board</h1>
                            </div>
                            <div className="flex items-center gap-2">
                                {/* View Toggle */}
                                <div className="flex bg-white bg-opacity-20 rounded-lg p-1">
                                    <button
                                        onClick={() => setViewMode('list')}
                                        className={`px-4 py-2 rounded-md font-medium transition-all ${
                                            viewMode === 'list'
                                                ? 'bg-white text-accent-600 shadow-sm'
                                                : 'text-white hover:bg-white hover:bg-opacity-10'
                                        }`}
                                    >
                                        List View
                                    </button>
                                    <button
                                        onClick={() => setViewMode('timeline')}
                                        className={`px-4 py-2 rounded-md font-medium transition-all ${
                                            viewMode === 'timeline'
                                                ? 'bg-white text-accent-600 shadow-sm'
                                                : 'text-white hover:bg-white hover:bg-opacity-10'
                                        }`}
                                    >
                                        Timeline View
                                    </button>
                                </div>
                                <button
                                    onClick={() => navigate('/job-log')}
                                    className="px-4 py-2 bg-white text-accent-600 rounded-lg font-medium shadow-sm hover:bg-accent-50 transition-all flex items-center gap-2"
                                >
                                    📋 Job Log
                                </button>
                            </div>
                        </div>
                    </div>

                    <div className="flex-1 overflow-hidden">
                        {loading && (
                            <div className="text-center py-12">
                                <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                                <p className="text-gray-600 font-medium">Loading jobs data...</p>
                            </div>
                        )}

                        {fetchError && !loading && (
                            <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-6 py-4 rounded-lg shadow-sm m-4">
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
                            <>
                                {viewMode === 'list' ? (
                                    <PMBoardList
                                        jobs={jobs}
                                        onUpdate={() => refetch(true)}
                                    />
                                ) : (
                                    <GanttChart
                                        filterComplete={true}
                                        onUpdate={() => refetch(true)}
                                    />
                                )}
                            </>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

export default PMBoard;

