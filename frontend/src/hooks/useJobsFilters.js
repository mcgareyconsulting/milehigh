import { useState, useMemo, useCallback } from 'react';

/**
 * Custom hook for managing filters in Jobs
 * @param {Array} jobs - The raw jobs data to filter
 * @returns {Object} Filter state, options, handlers, and filtered rows
 */
export function useJobsFilters(jobs = []) {
    // Filter state
    const [selectedProjectNames, setSelectedProjectNames] = useState([]); // Multi-select; empty = all
    const [selectedStages, setSelectedStages] = useState([]); // Array of selected stage values
    const [jobNumberSearch, setJobNumberSearch] = useState('');
    const [releaseNumberSearch, setReleaseNumberSearch] = useState('');
    const [selectedSubset, setSelectedSubset] = useState(null); // 'job_order', 'ready_to_ship', 'fab', or null for default

    /**
     * Check if a job matches all selected filters
     */
    const matchesSelectedFilter = useCallback((job) => {
        // Filter by project name (multi-select). If none selected, show all.
        if (selectedProjectNames.length > 0) {
            const jobName = job['Job'] ?? '';
            const normalized = String(jobName).trim();
            if (!selectedProjectNames.includes(normalized)) {
                return false;
            }
        }

        // Filter by Job # (must match if provided)
        if (jobNumberSearch.trim() !== '') {
            const searchTerm = jobNumberSearch.trim();
            const jobNumber = String(job['Job #'] ?? '').trim();
            if (!jobNumber.includes(searchTerm)) {
                return false;
            }
        }

        // Filter by Release # (must match if provided)
        if (releaseNumberSearch.trim() !== '') {
            const searchTerm = releaseNumberSearch.trim();
            const releaseNumber = String(job['Release #'] ?? '').trim();
            if (!releaseNumber.includes(searchTerm)) {
                return false;
            }
        }

        // Filter by Stage (multiselect - must match any selected stage)
        // If empty array, show all stages
        if (selectedStages.length > 0) {
            const jobStage = job['Stage'] ?? '';
            if (!selectedStages.includes(String(jobStage).trim())) {
                return false;
            }
        }

        return true;
    }, [selectedProjectNames, jobNumberSearch, releaseNumberSearch, selectedStages]);

    /**
     * Sort jobs by fab order (for subset-specific sorting)
     */
    const sortByFabOrder = useCallback((jobs) => {
        return [...jobs].sort((a, b) => {
            const fabOrderA = a['Fab Order'];
            const fabOrderB = b['Fab Order'];
            // Handle null/undefined values - put them at the end
            if (fabOrderA == null && fabOrderB == null) return 0;
            if (fabOrderA == null) return 1;
            if (fabOrderB == null) return -1;
            // Compare as numbers if possible, otherwise as strings
            const numA = Number(fabOrderA);
            const numB = Number(fabOrderB);
            if (!isNaN(numA) && !isNaN(numB)) {
                return numA - numB;
            }
            return String(fabOrderA).localeCompare(String(fabOrderB));
        });
    }, []);

    /**
     * Default sort: Job # ascending, then Release # ascending
     */
    const sortJobs = useCallback((filteredJobs) => {
        return filteredJobs.sort((a, b) => {
            // First sort by Job #
            if (a['Job #'] !== b['Job #']) {
                return (a['Job #'] || 0) - (b['Job #'] || 0);
            }
            // Then sort by Release # (treat as string for comparison)
            const releaseA = String(a['Release #'] || '').toLowerCase();
            const releaseB = String(b['Release #'] || '').toLowerCase();
            return releaseA.localeCompare(releaseB);
        });
    }, []);

    /**
     * Filter and sort jobs by stage_group independently
     * Each stage_group is sorted separately by fab_order, then combined in order
     */
    const filterAndSortByStageGroups = useCallback((jobsToFilter, stageGroups) => {
        const result = [];
        // Process each stage_group independently in order
        for (const stageGroup of stageGroups) {
            const filtered = jobsToFilter.filter(job => {
                const jobStageGroup = String(job['Stage Group'] ?? '').trim();
                return jobStageGroup === stageGroup;
            });
            const sorted = sortByFabOrder(filtered);
            result.push(...sorted);
        }
        return result;
    }, [sortByFabOrder]);

    /**
     * Filter jobs into Job Order subset (COMPLETE, READY_TO_SHIP, FABRICATION stage_groups)
     * Each stage_group is sorted independently by fab_order
     */
    const getJobOrderSubset = useCallback((jobsToFilter) => {
        return filterAndSortByStageGroups(jobsToFilter, ['COMPLETE', 'READY_TO_SHIP', 'FABRICATION']);
    }, [filterAndSortByStageGroups]);

    /**
     * Filter jobs into Fab subset (FABRICATION stage_group)
     */
    const getFabSubset = useCallback((jobsToFilter) => {
        const filtered = jobsToFilter.filter(job => {
            const stageGroup = String(job['Stage Group'] ?? '').trim();
            return stageGroup === 'FABRICATION';
        });
        return sortByFabOrder(filtered);
    }, [sortByFabOrder]);

    /**
     * Filtered and sorted jobs for display based on selected subset
     */
    const displayJobs = useMemo(() => {
        // First apply base filters (project name, job #, release #, etc.)
        const baseFiltered = jobs.filter(matchesSelectedFilter);

        // If no subset is selected, use default behavior
        if (!selectedSubset) {
            return sortJobs([...baseFiltered]);
        }

        // Apply subset-specific filtering
        let result = [];

        if (selectedSubset === 'job_order') {
            // Job Order: COMPLETE, READY_TO_SHIP, and FABRICATION stage_groups
            result = getJobOrderSubset(baseFiltered);
        } else if (selectedSubset === 'ready_to_ship') {
            // Ready to Ship: READY_TO_SHIP stage_group + FABRICATION stage_group (trailing filter)
            // Each stage_group is sorted independently by fab_order
            result = filterAndSortByStageGroups(baseFiltered, ['READY_TO_SHIP', 'FABRICATION']);
        } else if (selectedSubset === 'fab') {
            // Fab: Only FABRICATION stage_group
            result = getFabSubset(baseFiltered);
        }

        return result;
    }, [jobs, matchesSelectedFilter, sortJobs, selectedSubset, getJobOrderSubset, getFabSubset, filterAndSortByStageGroups]);

    /**
     * Extract unique project name (Job) options from jobs
     */
    const projectNameOptions = useMemo(() => {
        const values = new Set();
        jobs.forEach((job) => {
            const value = job['Job'];
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                values.add(String(value).trim());
            }
        });
        return Array.from(values).sort((a, b) => a.localeCompare(b));
    }, [jobs]);

    /**
     * Stage options for multiselect (using simplified labels)
     */
    const stageOptions = [
        { value: 'Released', label: 'Released' },
        { value: 'Cut start', label: 'Cut start' },
        { value: 'Material Ordered', label: 'Material Ordered' },
        { value: 'Fit Up Complete.', label: 'Fitup comp' },
        { value: 'Welded', label: 'Welded' },
        { value: 'Welded QC', label: 'Welded QC' },
        { value: 'Paint complete', label: 'Paint comp' },
        { value: 'Hold', label: 'Hold' },
        { value: 'Store at MHMW for shipping', label: 'Store' },
        { value: 'Shipping planning', label: 'Ship plan' },
        { value: 'Shipping completed', label: 'Ship comp' },
        { value: 'Complete', label: 'Complete' }
    ];

    /**
     * Color mapping for each stage (matching dropdown colors)
     * Unselected: lighter background, selected: darker background with white text
     */
    const stageColors = {
        'Released': {
            unselected: 'bg-blue-100 text-blue-800 border-blue-300',
            selected: 'bg-blue-600 text-white border-blue-700'
        },
        'Cut start': {
            unselected: 'bg-blue-100 text-blue-800 border-blue-300',
            selected: 'bg-blue-600 text-white border-blue-700'
        },
        'Fit Up Complete.': {
            unselected: 'bg-blue-100 text-blue-800 border-blue-300',
            selected: 'bg-blue-600 text-white border-blue-700'
        },
        'Welded QC': {
            unselected: 'bg-yellow-100 text-yellow-800 border-yellow-300',
            selected: 'bg-yellow-600 text-white border-yellow-700'
        },
        'Paint complete': {
            unselected: 'bg-emerald-100 text-emerald-800 border-emerald-300',
            selected: 'bg-emerald-600 text-white border-emerald-700'
        },
        'Store at MHMW for shipping': {
            unselected: 'bg-emerald-100 text-emerald-800 border-emerald-300',
            selected: 'bg-emerald-600 text-white border-emerald-700'
        },
        'Shipping planning': {
            unselected: 'bg-emerald-100 text-emerald-800 border-emerald-300',
            selected: 'bg-emerald-600 text-white border-emerald-700'
        },
        'Shipping completed': {
            unselected: 'bg-violet-100 text-violet-800 border-violet-300',
            selected: 'bg-violet-600 text-white border-violet-700'
        },
        'Complete': {
            unselected: 'bg-violet-100 text-violet-800 border-violet-300',
            selected: 'bg-violet-600 text-white border-violet-700'
        },
        'Hold': {
            unselected: 'bg-blue-100 text-blue-800 border-blue-300',
            selected: 'bg-blue-600 text-white border-blue-700'
        },
        'Welded': {
            unselected: 'bg-blue-100 text-blue-800 border-blue-300',
            selected: 'bg-blue-600 text-white border-blue-700'
        },
        'Material Ordered': {
            unselected: 'bg-blue-100 text-blue-800 border-blue-300',
            selected: 'bg-blue-600 text-white border-blue-700'
        }
    };

    /**
     * Toggle stage selection
     */
    const toggleStage = useCallback((stageValue) => {
        setSelectedStages(prev => {
            if (prev.includes(stageValue)) {
                return prev.filter(s => s !== stageValue);
            } else {
                return [...prev, stageValue];
            }
        });
    }, []);

    /**
     * Reset all filters to default values
     */
    const resetFilters = useCallback(() => {
        setSelectedProjectNames([]);
        setSelectedStages([]);
        setJobNumberSearch('');
        setReleaseNumberSearch('');
        setSelectedSubset(null);
    }, []);

    return {
        // Filter state
        selectedProjectNames,
        selectedStages,
        jobNumberSearch,
        releaseNumberSearch,
        selectedSubset,

        // Filter setters
        setSelectedProjectNames,
        setSelectedStages,
        setJobNumberSearch,
        setReleaseNumberSearch,
        setSelectedSubset,

        // Filter options
        projectNameOptions,
        stageOptions,
        stageColors,

        // Filtered and sorted jobs
        displayJobs,

        // Actions
        resetFilters,
        toggleStage,
    };
}