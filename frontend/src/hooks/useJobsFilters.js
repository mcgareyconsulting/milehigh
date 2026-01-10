import { useState, useMemo, useCallback } from 'react';

const ALL_OPTION_VALUE = '__ALL__';

/**
 * Custom hook for managing filters in Jobs
 * @param {Array} jobs - The raw jobs data to filter
 * @returns {Object} Filter state, options, handlers, and filtered rows
 */
export function useJobsFilters(jobs = []) {
    // Filter state
    const [selectedProjectName, setSelectedProjectName] = useState(ALL_OPTION_VALUE);
    const [selectedStages, setSelectedStages] = useState([]); // Array of selected stage values
    const [jobNumberSearch, setJobNumberSearch] = useState('');
    const [releaseNumberSearch, setReleaseNumberSearch] = useState('');
    const [sortBy, setSortBy] = useState('default'); // 'default' or 'fab_order_asc'
    const [showNotComplete, setShowNotComplete] = useState(false); // Filter to show only incomplete jobs
    const [showNotShippingComplete, setShowNotShippingComplete] = useState(false); // Filter to exclude Shipping completed stage
    const [showBeforePaintComplete, setShowBeforePaintComplete] = useState(false); // Filter to show only Released, Cut start, Fit Up Complete.

    /**
     * Check if a job matches all selected filters
     */
    const matchesSelectedFilter = useCallback((job) => {
        // Filter by project name
        if (selectedProjectName !== ALL_OPTION_VALUE) {
            const jobName = job['Job'] ?? '';
            if (String(jobName).trim() !== selectedProjectName) {
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

        // Filter by completion status - exclude jobs with 'X' in Job Comp
        if (showNotComplete) {
            const jobComp = String(job['Job Comp'] ?? '').trim().toUpperCase();
            if (jobComp === 'X') {
                return false;
            }
        }

        // Filter by stage - exclude jobs with 'Shipping completed' stage
        if (showNotShippingComplete) {
            const jobStage = String(job['Stage'] ?? '').trim();
            if (jobStage === 'Shipping completed') {
                return false;
            }
        }

        // Filter by stage - only show Released, Cut start, Fit Up Complete.
        if (showBeforePaintComplete) {
            const jobStage = String(job['Stage'] ?? '').trim();
            const allowedStages = ['Released', 'Cut start', 'Fit Up Complete.'];
            if (!allowedStages.includes(jobStage)) {
                return false;
            }
        }

        return true;
    }, [selectedProjectName, jobNumberSearch, releaseNumberSearch, selectedStages, showNotComplete, showNotShippingComplete, showBeforePaintComplete]);

    /**
     * Sort jobs based on current sortBy state
     */
    const sortJobs = useCallback((filteredJobs) => {
        if (sortBy === 'fab_order_asc') {
            return filteredJobs.sort((a, b) => {
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
        }
        // Default sort: Job # ascending, then Release # ascending
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
    }, [sortBy]);

    /**
     * Filtered and sorted jobs for display
     */
    const displayJobs = useMemo(() => {
        const filtered = jobs.filter(matchesSelectedFilter);
        return sortJobs([...filtered]); // Create a copy to avoid mutating the filtered array
    }, [jobs, matchesSelectedFilter, sortJobs]);

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
        { value: 'Fit Up Complete.', label: 'Fitup comp' },
        { value: 'Paint complete', label: 'Paint comp' },
        { value: 'Store at MHMW for shipping', label: 'Store' },
        { value: 'Shipping planning', label: 'Ship plan' },
        { value: 'Shipping completed', label: 'Ship comp' }
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
            unselected: 'bg-purple-100 text-purple-800 border-purple-300',
            selected: 'bg-purple-600 text-white border-purple-700'
        },
        'Fit Up Complete.': {
            unselected: 'bg-green-100 text-green-800 border-green-300',
            selected: 'bg-green-600 text-white border-green-700'
        },
        'Paint complete': {
            unselected: 'bg-yellow-100 text-yellow-800 border-yellow-300',
            selected: 'bg-yellow-600 text-white border-yellow-700'
        },
        'Store at MHMW for shipping': {
            unselected: 'bg-orange-100 text-orange-800 border-orange-300',
            selected: 'bg-orange-600 text-white border-orange-700'
        },
        'Shipping planning': {
            unselected: 'bg-indigo-100 text-indigo-800 border-indigo-300',
            selected: 'bg-indigo-600 text-white border-indigo-700'
        },
        'Shipping completed': {
            unselected: 'bg-gray-100 text-gray-800 border-gray-300',
            selected: 'bg-gray-600 text-white border-gray-700'
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
        setSelectedProjectName(ALL_OPTION_VALUE);
        setSelectedStages([]);
        setJobNumberSearch('');
        setReleaseNumberSearch('');
        setSortBy('default');
        setShowNotComplete(false);
        setShowNotShippingComplete(false);
        setShowBeforePaintComplete(false);
    }, []);

    return {
        // Filter state
        selectedProjectName,
        selectedStages,
        jobNumberSearch,
        releaseNumberSearch,
        sortBy,
        showNotComplete,
        showNotShippingComplete,
        showBeforePaintComplete,

        // Filter setters
        setSelectedProjectName,
        setSelectedStages,
        setJobNumberSearch,
        setReleaseNumberSearch,
        setSortBy,
        setShowNotComplete,
        setShowNotShippingComplete,
        setShowBeforePaintComplete,

        // Filter options
        projectNameOptions,
        stageOptions,
        stageColors,

        // Filtered and sorted jobs
        displayJobs,

        // Actions
        resetFilters,
        toggleStage,

        // Constants
        ALL_OPTION_VALUE,
    };
}