import { useState, useCallback } from 'react';

/**
 * All jobs share one unified fab_order pool.
 * Fixed-tier stages (fab_order 1 or 2) are not draggable.
 */
const FIXED_TIER_STAGES = new Set([
    'Shipping completed', 'Shipping Complete', 'Complete',
    'Paint complete', 'Paint Complete',
    'Store at MHMW for shipping', 'Store at Shop',
    'Shipping planning', 'Shipping Planning',
]);

function isFixedTierJob(job) {
    const stage = String(job['Stage'] ?? '').trim();
    return FIXED_TIER_STAGES.has(stage);
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
function calculateTopFabOrder(draggedJob, allJobs) {
    // Only consider dynamic jobs (fab_order > 2)
    const dynamicJobs = allJobs.filter(job => !isFixedTierJob(job));

    if (dynamicJobs.length === 0) {
        return 3;
    }

    // Sort by current fab order
    const sortedJobs = [...dynamicJobs].sort((a, b) => {
        const orderA = parseFabOrder(a);
        const orderB = parseFabOrder(b);
        return orderA - orderB;
    });

    // Dynamic fab_orders start at 3, so top position is 3
    return 3;
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
            // Don't allow dropping onto fixed-tier jobs
            if (isFixedTierJob(targetJob)) {
                setDragOverIndex(null);
            } else {
                setDragOverIndex(index);
            }
        }
    }, [draggedJob, displayJobs]);

    const handleDragLeave = useCallback((e) => {
        // Only clear if we're actually leaving the row (not just moving between child elements)
        if (!e.currentTarget.contains(e.relatedTarget)) {
            setDragOverIndex(null);
        }
    }, []);

    const handleDrop = useCallback(async (e, targetIndex, targetJob) => {
        e.preventDefault();

        if (!draggedJob) return;

        // Don't allow dropping fixed-tier jobs or dropping onto fixed-tier targets
        if (isFixedTierJob(draggedJob) || isFixedTierJob(targetJob)) {
            setDraggedIndex(null);
            setDragOverIndex(null);
            setDraggedJob(null);
            return;
        }

        // Work with all dynamic jobs (fab_order > 2), sorted by fab_order
        const draggedJobId = getJobId(draggedJob);
        const targetJobId = getJobId(targetJob);

        const dynamicJobs = jobs.filter(job => !isFixedTierJob(job));

        // Sort by fab order (nulls at end)
        const sortedGroup = [...dynamicJobs].sort((a, b) => {
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
            insertIndex = targetPosition;
        } else {
            insertIndex = targetPosition;
        }

        // Insert dragged job at the calculated position
        const newSortedGroup = [
            ...groupWithoutDragged.slice(0, insertIndex),
            draggedJob,
            ...groupWithoutDragged.slice(insertIndex)
        ];

        // Calculate new fab order: position + 3 (dynamic range starts at 3)
        let newFabOrder;

        if (insertIndex === 0) {
            // Top of dynamic range
            newFabOrder = 3;
        } else {
            // Use the fab_order of the job before this position + 1
            const jobBefore = newSortedGroup[insertIndex - 1];
            const orderBefore = parseFabOrder(jobBefore, 2);
            newFabOrder = Math.max(3, Math.floor(orderBefore) + 1);
        }

        // Update the dragged job — backend handles collision cascade
        await updateFabOrder(draggedJob['Job #'], draggedJob['Release #'], newFabOrder);

        // Reset drag state
        setDraggedIndex(null);
        setDragOverIndex(null);
        setDraggedJob(null);
    }, [draggedJob, jobs, updateFabOrder]);

    return {
        draggedIndex,
        dragOverIndex,
        handleDragStart,
        handleDragOver,
        handleDragLeave,
        handleDrop,
    };
}

