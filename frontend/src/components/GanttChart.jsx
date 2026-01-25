import React, { useState, useEffect, useMemo } from 'react';
import { jobsApi } from '../services/jobsApi';

function GanttChart({ filterComplete = false, onUpdate }) {
    const [projects, setProjects] = useState([]);
    const [allJobs, setAllJobs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [hoveredItem, setHoveredItem] = useState(null);
    const [hoverPosition, setHoverPosition] = useState({ x: 0, y: 0 });

    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);
                setError(null);
                
                // Fetch both gantt data and all jobs (for filtering)
                const [ganttData, jobs] = await Promise.all([
                    jobsApi.fetchGanttData(),
                    filterComplete ? jobsApi.fetchAllJobs() : Promise.resolve([])
                ]);
                
                setAllJobs(jobs);
                
                let filteredProjects = ganttData.projects || [];
                
                // Filter out Complete jobs if filterComplete is true
                if (filterComplete && jobs.length > 0) {
                    // Create a set of job-release combinations that are NOT Complete
                    // Normalize to strings for consistent matching
                    const nonCompleteJobs = new Set();
                    jobs.forEach(job => {
                        if (job['Stage'] !== 'Complete') {
                            const jobNum = String(job['Job #'] || '').trim();
                            const releaseNum = String(job['Release #'] || '').trim();
                            if (jobNum && releaseNum) {
                                nonCompleteJobs.add(`${jobNum}-${releaseNum}`);
                            }
                        }
                    });
                    
                    // Filter projects and releases
                    filteredProjects = filteredProjects
                        .map(project => {
                            const filteredReleases = project.releases.filter(release => {
                                const jobNum = String(release.job || '').trim();
                                const releaseNum = String(release.release || '').trim();
                                const jobKey = `${jobNum}-${releaseNum}`;
                                return nonCompleteJobs.has(jobKey);
                            });
                            
                            // Only include project if it has releases after filtering
                            if (filteredReleases.length === 0) {
                                return null;
                            }
                            
                            // Recalculate project dates based on filtered releases
                            const releaseDates = filteredReleases
                                .map(r => r.startDate ? new Date(r.startDate) : null)
                                .filter(d => d !== null);
                            const releaseEndDates = filteredReleases
                                .map(r => r.endDate ? new Date(r.endDate) : null)
                                .filter(d => d !== null);
                            
                            return {
                                ...project,
                                releases: filteredReleases,
                                startDate: releaseDates.length > 0 
                                    ? new Date(Math.min(...releaseDates)).toISOString().split('T')[0]
                                    : project.startDate,
                                endDate: releaseEndDates.length > 0
                                    ? new Date(Math.max(...releaseEndDates)).toISOString().split('T')[0]
                                    : project.endDate
                            };
                        })
                        .filter(project => project !== null);
                }
                
                setProjects(filteredProjects);
            } catch (err) {
                setError(err.message || 'Failed to load Gantt chart data');
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [filterComplete, onUpdate]);

    // Calculate timeline: get all dates and create day-based grid
    const timeline = useMemo(() => {
        if (projects.length === 0) return { days: [], startDate: null, endDate: null };

        const allDates = [];
        projects.forEach(project => {
            if (project.startDate) allDates.push(new Date(project.startDate));
            if (project.endDate) allDates.push(new Date(project.endDate));
            project.releases.forEach(release => {
                if (release.startDate) allDates.push(new Date(release.startDate));
                if (release.endDate) allDates.push(new Date(release.endDate));
            });
        });

        if (allDates.length === 0) return { days: [], startDate: null, endDate: null };

        const minDate = new Date(Math.min(...allDates));
        const maxDate = new Date(Math.max(...allDates));

        // Add some padding (7 days before and after)
        const startDate = new Date(minDate);
        startDate.setDate(startDate.getDate() - 7);
        const endDate = new Date(maxDate);
        endDate.setDate(endDate.getDate() + 7);

        // Generate array of all days
        const days = [];
        const currentDate = new Date(startDate);
        while (currentDate <= endDate) {
            days.push(new Date(currentDate));
            currentDate.setDate(currentDate.getDate() + 1);
        }

        return { days, startDate, endDate };
    }, [projects]);

    // Calculate position and width for a date range
    const calculateBarPosition = (startDateStr, endDateStr) => {
        if (!startDateStr || !endDateStr || timeline.days.length === 0) {
            return { left: 0, width: 0 };
        }

        const start = new Date(startDateStr);
        const end = new Date(endDateStr);
        const timelineStart = timeline.startDate;

        // Find the day indices
        const startIndex = timeline.days.findIndex(day => 
            day.toDateString() === start.toDateString()
        );
        const endIndex = timeline.days.findIndex(day => 
            day.toDateString() === end.toDateString()
        );

        if (startIndex === -1 || endIndex === -1) {
            return { left: 0, width: 0 };
        }

        // Calculate percentage positions
        const totalDays = timeline.days.length;
        const leftPercent = (startIndex / totalDays) * 100;
        const widthPercent = ((endIndex - startIndex + 1) / totalDays) * 100;

        return { left: leftPercent, width: widthPercent };
    };

    const formatDate = (dateStr) => {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    };

    const formatDateShort = (dateStr) => {
        if (!dateStr) return '';
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    };

    const handleMouseMove = (e, item) => {
        setHoveredItem(item);
        setHoverPosition({ x: e.clientX, y: e.clientY });
    };

    const handleMouseLeave = () => {
        setHoveredItem(null);
    };

    // Group days by month for header display
    const monthHeaders = useMemo(() => {
        if (timeline.days.length === 0) return [];

        const months = [];
        let currentMonth = null;
        let monthStartIndex = 0;

        timeline.days.forEach((day, index) => {
            const monthKey = `${day.getFullYear()}-${day.getMonth()}`;

            if (currentMonth !== monthKey) {
                if (currentMonth !== null) {
                    months.push({
                        monthKey: currentMonth,
                        startIndex: monthStartIndex,
                        endIndex: index - 1
                    });
                }
                currentMonth = monthKey;
                monthStartIndex = index;
            }
        });

        // Add the last month
        if (currentMonth !== null) {
            months.push({
                monthKey: currentMonth,
                startIndex: monthStartIndex,
                endIndex: timeline.days.length - 1
            });
        }

        return months.map(month => {
            const firstDay = timeline.days[month.startIndex];
            const monthName = firstDay.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
            return {
                name: monthName,
                startPercent: (month.startIndex / timeline.days.length) * 100,
                widthPercent: ((month.endIndex - month.startIndex + 1) / timeline.days.length) * 100
            };
        });
    }, [timeline.days]);

    return (
        <>
            <div className="flex-1 overflow-auto p-4 h-full">
                {loading && (
                    <div className="text-center py-12">
                        <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-500 mb-4"></div>
                        <p className="text-gray-600 font-medium">Loading Gantt chart data...</p>
                    </div>
                )}

                {error && (
                    <div className="bg-red-50 border-l-4 border-red-500 text-red-700 px-6 py-4 rounded-lg shadow-sm">
                        <div className="flex items-start">
                            <span className="text-xl mr-3">⚠️</span>
                            <div>
                                <p className="font-semibold">Unable to load Gantt chart data</p>
                                <p className="text-sm mt-1">{error}</p>
                            </div>
                        </div>
                    </div>
                )}

                {!loading && !error && projects.length > 0 && (
                    <div className="relative">
                        {/* Timeline Header */}
                        <div className="sticky top-0 bg-gray-100 border-b-2 border-gray-300 z-20 mb-2">
                            <div className="flex" style={{ minHeight: '50px' }}>
                                <div className="w-48 flex-shrink-0 border-r-2 border-gray-300 bg-gray-100 px-2 py-2">
                                    <span className="text-xs font-bold text-gray-700">Project / Release</span>
                                </div>
                                <div className="flex-1 relative" style={{ minHeight: '50px' }}>
                                    {monthHeaders.map((month, idx) => (
                                        <div
                                            key={idx}
                                            className="absolute border-r border-gray-300 text-center text-xs font-semibold text-gray-700 py-2 flex items-center justify-center"
                                            style={{
                                                left: `${month.startPercent}%`,
                                                width: `${month.widthPercent}%`,
                                                height: '100%'
                                            }}
                                        >
                                            {month.name}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>

                        {/* Gantt Chart Rows */}
                        <div className="space-y-1">
                            {projects.map((project, projectIdx) => {
                                const projectBar = calculateBarPosition(project.startDate, project.endDate);
                                
                                return (
                                    <div key={projectIdx} className="space-y-0.5">
                                        {/* Project Bar */}
                                        <div className="flex items-center" style={{ minHeight: '40px' }}>
                                            <div className="w-48 flex-shrink-0 border-r-2 border-gray-300 bg-gray-50 px-2 py-1 flex items-center">
                                                <span className="text-sm font-bold text-gray-800">
                                                    Project {project.project}
                                                </span>
                                            </div>
                                            <div className="flex-1 relative h-8 bg-gray-50">
                                                <div
                                                    className="absolute h-8 rounded-md shadow-md flex items-center px-2"
                                                    style={{
                                                        left: `${projectBar.left}%`,
                                                        width: `${projectBar.width}%`,
                                                        backgroundColor: project.color,
                                                        minWidth: projectBar.width < 0.5 ? '2px' : 'auto'
                                                    }}
                                                    onMouseMove={(e) => handleMouseMove(e, {
                                                        type: 'project',
                                                        project: project.project,
                                                        projectName: project.projectName,
                                                        startDate: project.startDate,
                                                        endDate: project.endDate
                                                    })}
                                                    onMouseLeave={handleMouseLeave}
                                                >
                                                    <span className="text-white text-xs font-semibold truncate">
                                                        {project.projectName}
                                                    </span>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Release Bars */}
                                        {project.releases.map((release, releaseIdx) => {
                                            const releaseBar = calculateBarPosition(release.startDate, release.endDate);
                                            
                                            return (
                                                <div key={releaseIdx} className="flex items-center" style={{ minHeight: '28px' }}>
                                                    <div className="w-48 flex-shrink-0 border-r-2 border-gray-300 bg-white px-2 py-1 flex items-center pl-6">
                                                        <span className="text-xs text-gray-600">
                                                            {release.job}-{release.release}
                                                        </span>
                                                    </div>
                                                    <div className="flex-1 relative h-6 bg-white">
                                                        <div
                                                            className="absolute h-6 rounded shadow-sm flex items-center px-1"
                                                            style={{
                                                                left: `${releaseBar.left}%`,
                                                                width: `${releaseBar.width}%`,
                                                                backgroundColor: project.color,
                                                                opacity: 0.7,
                                                                minWidth: releaseBar.width < 0.5 ? '2px' : 'auto'
                                                            }}
                                                            onMouseMove={(e) => handleMouseMove(e, {
                                                                type: 'release',
                                                                job: release.job,
                                                                release: release.release,
                                                                jobName: release.jobName,
                                                                description: release.description,
                                                                startDate: release.startDate,
                                                                endDate: release.endDate,
                                                                pm: release.pm,
                                                                by: release.by
                                                            })}
                                                            onMouseLeave={handleMouseLeave}
                                                        >
                                                            <span className="text-white text-[10px] font-medium truncate">
                                                                {release.job}-{release.release}
                                                            </span>
                                                        </div>
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}

                {!loading && !error && projects.length === 0 && (
                    <div className="text-center py-12">
                        <p className="text-gray-600 font-medium">No projects with start install dates found.</p>
                    </div>
                )}
            </div>
            {hoveredItem && (
                <div
                    className="fixed bg-gray-900 text-white text-xs rounded-lg shadow-xl p-3 z-50 pointer-events-none"
                    style={{
                        left: `${hoverPosition.x + 10}px`,
                        top: `${hoverPosition.y + 10}px`,
                        maxWidth: '300px'
                    }}
                >
                    {hoveredItem.type === 'project' ? (
                        <>
                            <div className="font-bold mb-1">Project {hoveredItem.project}</div>
                            <div className="text-gray-300">{hoveredItem.projectName}</div>
                            <div className="mt-2 pt-2 border-t border-gray-700">
                                <div>Start: {formatDate(hoveredItem.startDate)}</div>
                                <div>End: {formatDate(hoveredItem.endDate)}</div>
                            </div>
                        </>
                    ) : (
                        <>
                            <div className="font-bold mb-1">Job {hoveredItem.job}-{hoveredItem.release}</div>
                            <div className="text-gray-300">{hoveredItem.jobName}</div>
                            {hoveredItem.description && (
                                <div className="text-gray-400 text-[10px] mt-1">{hoveredItem.description}</div>
                            )}
                            <div className="mt-2 pt-2 border-t border-gray-700">
                                <div>Start Install: {formatDate(hoveredItem.startDate)}</div>
                                <div>Comp ETA: {formatDate(hoveredItem.endDate)}</div>
                                {hoveredItem.pm && <div>PM: {hoveredItem.pm}</div>}
                                {hoveredItem.by && <div>BY: {hoveredItem.by}</div>}
                            </div>
                        </>
                    )}
                </div>
            )}
        </>
    );
}

export default GanttChart;

