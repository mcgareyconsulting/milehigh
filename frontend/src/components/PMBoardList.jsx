import React, { useState, useMemo } from 'react';
import { jobsApi } from '../services/jobsApi';

function PMBoardList({ jobs, onUpdate }) {
    // Stage options matching JobsTableRow
    const stageOptions = [
        { value: 'Released', label: 'Released' },
        { value: 'Cut start', label: 'Cut start' },
        { value: 'Fit Up Complete.', label: 'Fitup comp' },
        { value: 'Welded QC', label: 'Welded QC' },
        { value: 'Paint complete', label: 'Paint comp' },
        { value: 'Store at MHMW for shipping', label: 'Store' },
        { value: 'Shipping planning', label: 'Ship plan' },
        { value: 'Shipping completed', label: 'Ship comp' },
        { value: 'Complete', label: 'Complete' }
    ];

    // Color mapping for each stage (matching JobsTableRow)
    const stageColors = {
        'Released': {
            light: 'rgb(219 234 254)',
            base: 'rgb(59 130 246)',
            text: 'rgb(30 64 175)',
            border: 'rgb(147 197 253)',
        },
        'Cut start': {
            light: 'rgb(219 234 254)',
            base: 'rgb(59 130 246)',
            text: 'rgb(30 64 175)',
            border: 'rgb(147 197 253)',
        },
        'Fit Up Complete.': {
            light: 'rgb(219 234 254)',
            base: 'rgb(59 130 246)',
            text: 'rgb(30 64 175)',
            border: 'rgb(147 197 253)',
        },
        'Welded QC': {
            light: 'rgb(219 234 254)',
            base: 'rgb(59 130 246)',
            text: 'rgb(30 64 175)',
            border: 'rgb(147 197 253)',
        },
        'Paint complete': {
            light: 'rgb(254 249 195)',
            base: 'rgb(234 179 8)',
            text: 'rgb(133 77 14)',
            border: 'rgb(253 224 71)',
        },
        'Store at MHMW for shipping': {
            light: 'rgb(254 249 195)',
            base: 'rgb(234 179 8)',
            text: 'rgb(133 77 14)',
            border: 'rgb(253 224 71)',
        },
        'Shipping planning': {
            light: 'rgb(254 249 195)',
            base: 'rgb(234 179 8)',
            text: 'rgb(133 77 14)',
            border: 'rgb(253 224 71)',
        },
        'Shipping completed': {
            light: 'rgb(209 250 229)',
            base: 'rgb(16 185 129)',
            text: 'rgb(6 95 70)',
            border: 'rgb(110 231 183)',
        },
        'Complete': {
            light: 'rgb(209 250 229)',
            base: 'rgb(16 185 129)',
            text: 'rgb(6 95 70)',
            border: 'rgb(110 231 183)',
        }
    };

    const [draggedJob, setDraggedJob] = useState(null);
    const [dragOverColumn, setDragOverColumn] = useState(null);
    const [updatingJobs, setUpdatingJobs] = useState(new Set());

    // Group jobs by stage
    const jobsByStage = useMemo(() => {
        const grouped = {};
        stageOptions.forEach(stage => {
            grouped[stage.value] = [];
        });

        jobs.forEach(job => {
            const stage = job['Stage'] || 'Released';
            if (grouped[stage]) {
                grouped[stage].push(job);
            } else {
                // If stage not in our list, add to Released
                grouped['Released'].push(job);
            }
        });

        // Sort jobs within each stage by Fab Order
        Object.keys(grouped).forEach(stage => {
            grouped[stage].sort((a, b) => {
                const orderA = a['Fab Order'] ?? 999999;
                const orderB = b['Fab Order'] ?? 999999;
                return orderA - orderB;
            });
        });

        return grouped;
    }, [jobs]);

    const formatDate = (dateValue) => {
        if (!dateValue) return '—';
        try {
            const date = new Date(dateValue);
            if (isNaN(date.getTime())) return '—';
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const day = String(date.getDate()).padStart(2, '0');
            const year = String(date.getFullYear()).slice(-2);
            return `${month}/${day}/${year}`;
        } catch (e) {
            return '—';
        }
    };

    const handleDragStart = (e, job) => {
        setDraggedJob(job);
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/html', '');
    };

    const handleDragOver = (e, stage) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        setDragOverColumn(stage);
    };

    const handleDragLeave = () => {
        setDragOverColumn(null);
    };

    const handleDrop = async (e, targetStage) => {
        e.preventDefault();
        setDragOverColumn(null);

        if (!draggedJob) return;

        const currentStage = draggedJob['Stage'] || 'Released';
        if (currentStage === targetStage) {
            setDraggedJob(null);
            return;
        }

        // Update the job's stage
        const jobId = `${draggedJob['Job #']}-${draggedJob['Release #']}`;
        setUpdatingJobs(prev => new Set(prev).add(jobId));

        try {
            await jobsApi.updateStage(draggedJob['Job #'], draggedJob['Release #'], targetStage);
            
            // Trigger update to refresh data
            if (onUpdate) {
                onUpdate();
            }
        } catch (error) {
            console.error('Failed to update stage:', error);
            alert(`Failed to update stage: ${error.message}`);
        } finally {
            setUpdatingJobs(prev => {
                const next = new Set(prev);
                next.delete(jobId);
                return next;
            });
            setDraggedJob(null);
        }
    };

    const getJobCardStyle = (job, stage) => {
        const colors = stageColors[stage] || stageColors['Released'];
        return {
            backgroundColor: colors.light,
            borderColor: colors.border,
            color: colors.text,
        };
    };

    return (
        <div className="flex-1 overflow-auto p-4 bg-gray-100 h-full">
            <div className="flex gap-4 h-full">
                {stageOptions.map((stageOption) => {
                    const stage = stageOption.value;
                    const stageJobs = jobsByStage[stage] || [];
                    const colors = stageColors[stage] || stageColors['Released'];
                    const isDragOver = dragOverColumn === stage;

                    return (
                        <div
                            key={stage}
                            className={`flex-1 min-w-[280px] bg-gray-50 rounded-lg shadow-sm flex flex-col ${
                                isDragOver ? 'ring-2 ring-blue-400' : ''
                            }`}
                            onDragOver={(e) => handleDragOver(e, stage)}
                            onDragLeave={handleDragLeave}
                            onDrop={(e) => handleDrop(e, stage)}
                        >
                            {/* Column Header */}
                            <div
                                className="px-4 py-3 rounded-t-lg font-semibold text-sm text-white"
                                style={{
                                    backgroundColor: colors.base,
                                }}
                            >
                                <div className="flex items-center justify-between">
                                    <span>{stageOption.label}</span>
                                    <span className="bg-white bg-opacity-30 px-2 py-0.5 rounded text-xs">
                                        {stageJobs.length}
                                    </span>
                                </div>
                            </div>

                            {/* Column Content */}
                            <div className="flex-1 overflow-y-auto p-2 space-y-2">
                                {stageJobs.length === 0 ? (
                                    <div className="text-center text-gray-400 text-sm py-8">
                                        No jobs
                                    </div>
                                ) : (
                                    stageJobs.map((job) => {
                                        const jobId = `${job['Job #']}-${job['Release #']}`;
                                        const isUpdating = updatingJobs.has(jobId);
                                        const isDragging = draggedJob && 
                                            draggedJob['Job #'] === job['Job #'] && 
                                            draggedJob['Release #'] === job['Release #'];

                                        return (
                                            <div
                                                key={jobId}
                                                draggable={!isUpdating}
                                                onDragStart={(e) => handleDragStart(e, job)}
                                                className={`p-3 rounded-lg shadow-sm cursor-move transition-all border-2 ${
                                                    isDragging ? 'opacity-50' : ''
                                                } ${isUpdating ? 'opacity-50 cursor-wait' : 'hover:shadow-md'}`}
                                                style={getJobCardStyle(job, stage)}
                                            >
                                                <div className="font-semibold text-sm mb-1">
                                                    {job['Job #']}-{job['Release #']}
                                                </div>
                                                {job['Job'] && (
                                                    <div className="text-xs mb-1 font-medium truncate" title={job['Job']}>
                                                        {job['Job']}
                                                    </div>
                                                )}
                                                {job['Description'] && (
                                                    <div className="text-xs text-gray-600 mb-2 line-clamp-2" title={job['Description']}>
                                                        {job['Description']}
                                                    </div>
                                                )}
                                                <div className="flex flex-wrap gap-2 text-xs">
                                                    {job['PM'] && (
                                                        <span className="font-medium">PM: {job['PM']}</span>
                                                    )}
                                                    {job['BY'] && (
                                                        <span>BY: {job['BY']}</span>
                                                    )}
                                                </div>
                                                {job['Released'] && (
                                                    <div className="text-xs mt-2 pt-2 border-t border-opacity-30">
                                                        Released: {formatDate(job['Released'])}
                                                    </div>
                                                )}
                                                {job['Fab Order'] !== null && job['Fab Order'] !== undefined && (
                                                    <div className="text-xs mt-1">
                                                        Fab Order: {job['Fab Order']}
                                                    </div>
                                                )}
                                            </div>
                                        );
                                    })
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

export default PMBoardList;

