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

        // Sort by fab order (nulls at end)
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

        // Remove dragged job from sorted list to calculate new position
        const groupWithoutDragged = sortedGroup.filter(j => getJobId(j) !== draggedJobId);

        // Determine where to insert based on drag direction
        let insertIndex;
        if (draggedPosition < targetPosition) {
            // Dragging down - insert after target (target position stays same after removing dragged)
            insertIndex = targetPosition;
        } else {
            // Dragging up - insert before target (target position stays same after removing dragged)
            insertIndex = targetPosition;
        }

        // Insert dragged job at the calculated position
        const newSortedGroup = [
            ...groupWithoutDragged.slice(0, insertIndex),
            draggedJob,
            ...groupWithoutDragged.slice(insertIndex)
        ];

        // Calculate new fab order based on position in the new sorted group
        let newFabOrder;

        // Check if we're inserting at the top (position 0)
        if (insertIndex === 0) {
            // If there are jobs with decimal orders (< 1) at the top, use decimal bumping
            const firstJob = newSortedGroup.length > 1 ? newSortedGroup[1] : null;
            if (firstJob) {
                const firstOrder = parseFabOrder(firstJob, 1);
                if (firstOrder < 1) {
                    // Use decimal bumping
                    newFabOrder = calculateTopFabOrder(draggedJob, jobs, selectedSubset);
                } else {
                    // First job has order >= 1, so we become #1
                    newFabOrder = 1;
                }
            } else {
                // No other jobs, become #1
                newFabOrder = 1;
            }
        } else {
            // Inserting in middle or end
            // Count how many jobs with order >= 1 come before this position in the new sorted group
            let countBefore = 0;
            for (let i = 0; i < insertIndex; i++) {
                const job = newSortedGroup[i];
                const order = parseFabOrder(job, 999999);
                // Only count jobs with integer orders >= 1 (not decimals, not null)
                if (order >= 1 && order < 999999) {
                    countBefore += 1;
                }
            }
            // The new fab order is countBefore + 1
            newFabOrder = countBefore + 1;
        }

        // Update the dragged job
        await updateFabOrder(draggedJob['Job #'], draggedJob['Release #'], newFabOrder);

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

