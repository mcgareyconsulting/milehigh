import { useState, useCallback } from 'react';

/**
 * Get the staging subset that a job belongs to based on its stage_group
 * @param {Object} job - The job object
 * @returns {string} - 'job_order', 'ready_to_ship', 'fab', or null
 */
function getJobStagingSubset(job) {
    const stageGroup = String(job['Stage Group'] ?? '').trim();

    // Fab subset: FABRICATION stage_group
    if (stageGroup === 'FABRICATION') {
        return 'fab';
    }

    // Ready to Ship: READY_TO_SHIP stage_group
    if (stageGroup === 'READY_TO_SHIP') {
        return 'ready_to_ship';
    }

    // Job Order: all jobs (fallback, includes COMPLETE and any unmapped jobs)
    return 'job_order';
}

/**
 * Get a unique identifier for a job (job-release combination)
 */
function getJobId(job) {
    return `${job['Job #']}-${job['Release #']}`;
}

/**
 * Parse fab order as a number
 */
function parseFabOrder(job, fallback = 999999) {
    const raw = job['Fab Order'];
    if (raw === null || raw === undefined) return fallback;
    return typeof raw === 'number' ? raw : parseFloat(raw) || fallback;
}

/**
 * Calculate a new "top bump" fab order when moving a job above the current #1
 * for a given staging subset group.
 */
function calculateTopFabOrder(draggedJob, allJobs, selectedSubset) {
    const draggedSubset = selectedSubset || getJobStagingSubset(draggedJob);

    // Filter jobs to only those in the same staging subset
    const sameSubsetJobs = allJobs.filter(job => {
        const jobSubset = selectedSubset || getJobStagingSubset(job);
        return jobSubset === draggedSubset;
    });

    if (sameSubsetJobs.length === 0) {
        return 0.5;
    }

    // Sort by current fab order
    const sortedJobs = [...sameSubsetJobs].sort((a, b) => {
        const orderA = parseFabOrder(a);
        const orderB = parseFabOrder(b);
        return orderA - orderB;
    });

    const first = sortedJobs[0];
    const firstOrder = parseFabOrder(first, 1);

    // If the first order is an integer >= 1, just use 0.5
    if (firstOrder >= 1) {
        return 0.5;
    }

    // Otherwise, find the smallest positive order and halve it
    let minPositive = Infinity;
    for (const job of sortedJobs) {
        const val = parseFabOrder(job);
        if (!isNaN(val) && val > 0 && val < minPositive) {
            minPositive = val;
        }
    }

    const base = minPositive === Infinity ? 1 : minPositive;
    const newOrder = base / 2;

    // Round to reasonable precision (4 decimal places)
    return Math.round(newOrder * 10000) / 10000;
}

/**
 * Custom hook for managing drag and drop functionality in the job log table
 * @param {Array} jobs - All jobs (not filtered)
 * @param {Array} displayJobs - Filtered and displayed jobs
 * @param {Function} updateFabOrder - Function to update fab order (job, release, fabOrder)
 * @param {string|null} selectedSubset - The currently selected staging subset ('job_order', 'ready_to_ship', 'fab', or null)
 */
export function useJobsDragAndDrop(jobs, displayJobs, updateFabOrder, selectedSubset) {
    const [draggedIndex, setDraggedIndex] = useState(null);
    const [dragOverIndex, setDragOverIndex] = useState(null);
    const [draggedJob, setDraggedJob] = useState(null);

    const handleDragStart = useCallback((e, index, job) => {
        setDraggedIndex(index);
        setDraggedJob(job);
    }, []);

    const handleDragOver = useCallback((e, index) => {
        e.preventDefault();
        if (draggedJob) {
            const targetJob = displayJobs[index];
            const draggedSubset = selectedSubset || getJobStagingSubset(draggedJob);
            const targetSubset = selectedSubset || getJobStagingSubset(targetJob);

            // Only allow drag over if same staging subset
            if (draggedSubset === targetSubset) {
                setDragOverIndex(index);
            } else {
                setDragOverIndex(null);
            }
        }
    }, [draggedJob, displayJobs, selectedSubset]);

    const handleDragLeave = useCallback((e) => {
        // Only clear if we're actually leaving the row (not just moving between child elements)
        if (!e.currentTarget.contains(e.relatedTarget)) {
            setDragOverIndex(null);
        }
    }, []);

    const handleDrop = useCallback(async (e, targetIndex, targetJob) => {
        e.preventDefault();

        if (!draggedJob) return;

        const draggedSubset = selectedSubset || getJobStagingSubset(draggedJob);
        const targetSubset = selectedSubset || getJobStagingSubset(targetJob);

        // Only allow drop if same staging subset
        if (draggedSubset !== targetSubset) {
            setDraggedIndex(null);
            setDragOverIndex(null);
            setDraggedJob(null);
            return;
        }

        // Work with all jobs in this staging subset group, sorted by current fab order
        const draggedJobId = getJobId(draggedJob);
        const targetJobId = getJobId(targetJob);

        const sameSubsetJobs = jobs.filter(job => {
            const jobSubset = selectedSubset || getJobStagingSubset(job);
            return jobSubset === draggedSubset;
        });

        const sortedGroup = [...sameSubsetJobs].sort((a, b) => {
            const orderA = parseFabOrder(a);
            const orderB = parseFabOrder(b);
            return orderA - orderB;
        });

        const draggedPosition = sortedGroup.findIndex(j => getJobId(j) === draggedJobId);
        const targetPosition = sortedGroup.findIndex(j => getJobId(j) === targetJobId);

        if (draggedPosition === -1 || targetPosition === -1) {
            setDraggedIndex(null);
            setDragOverIndex(null);
            setDraggedJob(null);
            return;
        }

        // Case 1: moving above the current first item -> use decimal bumping
        if (targetPosition === 0 && draggedPosition !== 0) {
            const newFabOrder = calculateTopFabOrder(draggedJob, jobs, selectedSubset);
            await updateFabOrder(draggedJob['Job #'], draggedJob['Release #'], newFabOrder);
        } else {
            // Case 2: reordering in the middle or end
            // Count urgent rows (decimals < 1) that come before the target
            let urgentCount = 0;
            for (let i = 0; i < targetPosition; i++) {
                const job = sortedGroup[i];
                const currentOrderRaw = job['Fab Order'];
                const currentOrder = typeof currentOrderRaw === 'number'
                    ? currentOrderRaw
                    : currentOrderRaw !== null && currentOrderRaw !== undefined
                        ? parseFloat(currentOrderRaw)
                        : null;

                if (currentOrder !== null && !isNaN(currentOrder) && currentOrder > 0 && currentOrder < 1) {
                    urgentCount += 1;
                } else {
                    break;
                }
            }

            // Count rows with order >= 1 that come before the target (excluding the dragged row)
            let regularCountBeforeTarget = 0;
            for (let i = 0; i < targetPosition; i++) {
                const job = sortedGroup[i];
                if (getJobId(job) === draggedJobId) {
                    continue; // Skip the dragged row
                }
                const currentOrderRaw = job['Fab Order'];
                const currentOrder = typeof currentOrderRaw === 'number'
                    ? currentOrderRaw
                    : currentOrderRaw !== null && currentOrderRaw !== undefined
                        ? parseFloat(currentOrderRaw)
                        : null;

                // Only count rows with order >= 1 (not NULL, not decimals < 1)
                if (currentOrder !== null && !isNaN(currentOrder) && currentOrder >= 1) {
                    regularCountBeforeTarget += 1;
                }
            }

            // Determine insert position: if dragging down, insert after target; if up, before target
            let insertOffset = 0;
            if (draggedPosition < targetPosition) {
                // Dragging down - check if target row has order >= 1
                const targetOrderRaw = targetJob['Fab Order'];
                const targetOrder = typeof targetOrderRaw === 'number'
                    ? targetOrderRaw
                    : targetOrderRaw !== null && targetOrderRaw !== undefined
                        ? parseFloat(targetOrderRaw)
                        : null;

                // If target has order >= 1, insert after it; otherwise insert before
                if (targetOrder !== null && !isNaN(targetOrder) && targetOrder >= 1) {
                    insertOffset = 1;
                }
            }

            // Calculate target fab order number (1-based, after urgent decimals)
            const targetFabOrder = regularCountBeforeTarget + insertOffset + 1;

            // Update the dragged job
            await updateFabOrder(draggedJob['Job #'], draggedJob['Release #'], targetFabOrder);
        }

        // Reset drag state
        setDraggedIndex(null);
        setDragOverIndex(null);
        setDraggedJob(null);
    }, [draggedJob, jobs, updateFabOrder, selectedSubset]);

    return {
        draggedIndex,
        dragOverIndex,
        handleDragStart,
        handleDragOver,
        handleDragLeave,
        handleDrop,
    };
}

