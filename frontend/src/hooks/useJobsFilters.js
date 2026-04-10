import { useState, useMemo, useCallback, useEffect } from 'react';

const _FAB_MODIFIER = {
    'Released': 1.0,
    'Cut Start': 0.9, 'Cut start': 0.9,
    'Fit up Comp': 0.5, 'Fit Up Complete': 0.5, 'Fit Up Complete.': 0.5, 'Fitup comp': 0.5,
    'WeldingQC': 0.0, 'Welded QC': 0.0, 'Welding QC': 0.0, 'Welded': 0.0,
    'Paint Start': 0.0,
    'Paint Complete': 0.0, 'Paint complete': 0.0, 'Paint comp': 0.0,
    'Store': 0.0, 'Store at MHMW for shipping': 0.0,
    'Ship Planning': 0.0, 'Shipping planning': 0.0,
    'Ship Complete': 0.0, 'Shipping completed': 0.0,
    'Complete': 0.0,
};

function _getFabModifier(stage) {
    return stage in _FAB_MODIFIER ? _FAB_MODIFIER[stage] : 1.0;
}

function _parseJobComp(val) {
    if (val === null || val === undefined || val === '') return 0.0;
    const frac = parseFloat(val);
    if (isNaN(frac)) return 0.0;
    return Math.min(frac, 1.0);
}

/**
 * Custom hook for managing filters in Jobs
 * @param {Array} jobs - The raw jobs data to filter
 * @returns {Object} Filter state, options, handlers, and filtered rows
 */
export function useJobsFilters(jobs = []) {
    // Filter state (persisted to localStorage)
    const [selectedProjectNames, setSelectedProjectNames] = useState(
        () => JSON.parse(localStorage.getItem('jl_projects') || '[]')
    );
    const [selectedStages, setSelectedStages] = useState([]); // Array of selected stage values
    const [search, setSearch] = useState('');
    const [selectedSubset, setSelectedSubset] = useState(
        () => localStorage.getItem('jl_subset') || null
    ); // 'job_order', 'ready_to_ship', 'paint', 'paint_fab', 'fab', or null for default

    // Sync filter state to localStorage
    useEffect(() => { localStorage.setItem('jl_projects', JSON.stringify(selectedProjectNames)); }, [selectedProjectNames]);
    useEffect(() => {
        if (selectedSubset === null) {
            localStorage.removeItem('jl_subset');
        } else {
            localStorage.setItem('jl_subset', selectedSubset);
        }
    }, [selectedSubset]);

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

        // Unified search: loose keyword match across Job #, Release #, name, description
        if (search.trim() !== '') {
            const keywords = search.trim().toLowerCase().split(/\s+/);
            const haystack = [
                String(job['Job #'] ?? ''),
                String(job['Release #'] ?? ''),
                (job['Job'] || ''),
                (job['Description'] || ''),
            ].join(' ').toLowerCase();
            if (!keywords.every(kw => haystack.includes(kw))) {
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
    }, [selectedProjectNames, search, selectedStages]);

    /**
     * Stage priority for tiebreaking when fab_order values are equal
     * (e.g. all Ready-to-Ship fixed-tier stages share fab_order = 2)
     */
    const STAGE_SORT_PRIORITY = {
        'Shipping planning': 1,
        'Shipping Planning': 1,
        'Store at MHMW for shipping': 2,
        'Store at Shop': 2,
        'Paint complete': 3,
        'Paint Complete': 3,
        'Paint Start': 3.5,
        'Welded QC': 4,
    };

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
                if (numA !== numB) return numA - numB;
                // Tiebreak by stage priority within the same fab_order
                const prioA = STAGE_SORT_PRIORITY[a['Stage']] ?? 999;
                const prioB = STAGE_SORT_PRIORITY[b['Stage']] ?? 999;
                return prioA - prioB;
            }
            return String(fabOrderA).localeCompare(String(fabOrderB));
        });
    }, []);

    /**
     * Sort jobs by fab order, then start install date as tiebreaker (for Paint+Fab view)
     */
    const sortByFabOrderThenStartInstall = useCallback((jobs) => {
        return [...jobs].sort((a, b) => {
            const fabOrderA = a['Fab Order'];
            const fabOrderB = b['Fab Order'];
            if (fabOrderA == null && fabOrderB == null) return 0;
            if (fabOrderA == null) return 1;
            if (fabOrderB == null) return -1;
            const numA = Number(fabOrderA);
            const numB = Number(fabOrderB);
            if (!isNaN(numA) && !isNaN(numB)) {
                if (numA !== numB) return numA - numB;
                const dateA = a['Start install'] ? new Date(a['Start install']) : null;
                const dateB = b['Start install'] ? new Date(b['Start install']) : null;
                if (dateA && dateB && dateA.getTime() !== dateB.getTime()) return dateA - dateB;
                if (dateA && !dateB) return -1;
                if (!dateA && dateB) return 1;
                const prioA = STAGE_SORT_PRIORITY[a['Stage']] ?? 999;
                const prioB = STAGE_SORT_PRIORITY[b['Stage']] ?? 999;
                return prioA - prioB;
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
     * Filter jobs by stage_groups and sort by unified fab_order
     */
    const filterByStageGroups = useCallback((jobsToFilter, stageGroups) => {
        const filtered = jobsToFilter.filter(job => {
            const jobStageGroup = String(job['Stage Group'] ?? '').trim();
            return stageGroups.includes(jobStageGroup);
        });
        return sortByFabOrder(filtered);
    }, [sortByFabOrder]);

    /**
     * Job Order subset: all active releases sorted by unified fab_order
     */
    const getJobOrderSubset = useCallback((jobsToFilter) => {
        return sortByFabOrder([...jobsToFilter]);
    }, [sortByFabOrder]);

    /**
     * Filter jobs into Fab subset (FABRICATION stage_group)
     */
    const getFabSubset = useCallback((jobsToFilter) => {
        return filterByStageGroups(jobsToFilter, ['FABRICATION']);
    }, [filterByStageGroups]);

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
            // Job Order: all releases sorted by unified fab_order
            result = getJobOrderSubset(baseFiltered);
        } else if (selectedSubset === 'ready_to_ship') {
            // Ready to Ship: Shipping planning, Store at MHMW for shipping, Paint complete
            const readyToShipStages = ['Shipping planning', 'Store at MHMW for shipping', 'Paint complete'];
            const rtsOnly = baseFiltered.filter(job => readyToShipStages.includes(String(job['Stage'] ?? '').trim()));
            result = sortByFabOrder(rtsOnly);
        } else if (selectedSubset === 'paint') {
            // Paint: only Welded QC jobs, ascending fab order
            const paintStages = ['Welded QC', 'Paint Start'];
            const paintOnly = baseFiltered.filter(job => paintStages.includes(String(job['Stage'] ?? '').trim()));
            result = sortByFabOrder(paintOnly);
        } else if (selectedSubset === 'paint_fab') {
            // Paint+Fab: Paint complete + Welded QC, then FABRICATION group
            // Sorted by fab_order with start_install date as tiebreaker within same fab_order
            const paintStages = ['Paint complete', 'Welded QC', 'Paint Start'];
            const paintOnly = baseFiltered.filter(job => paintStages.includes(String(job['Stage'] ?? '').trim()));
            const paintSorted = sortByFabOrderThenStartInstall(paintOnly);
            const fabOnly = baseFiltered.filter(job => String(job['Stage Group'] ?? '').trim() === 'FABRICATION');
            const fabSorted = sortByFabOrderThenStartInstall(fabOnly);
            result = [...paintSorted, ...fabSorted];
        } else if (selectedSubset === 'fab') {
            // Fab: Only FABRICATION stage_group
            result = getFabSubset(baseFiltered);
        }

        return result;
    }, [jobs, matchesSelectedFilter, sortJobs, selectedSubset, getJobOrderSubset, getFabSubset, filterByStageGroups, sortByFabOrder, sortByFabOrderThenStartInstall]);

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
     * Stage → stage_group for subset-based dropdown colors (matches backend).
     * FABRICATION = Fab, READY_TO_SHIP = Ready to Ship, COMPLETE = Complete.
     */
    const stageToGroup = {
        'Released': 'FABRICATION',
        'Cut start': 'FABRICATION',
        'Cut Complete': 'FABRICATION',
        'Fitup Start': 'FABRICATION',
        'Fit Up Complete.': 'FABRICATION',
        'Weld Start': 'FABRICATION',
        'Weld Complete': 'FABRICATION',
        'Hold': 'FABRICATION',
        'Material Ordered': 'FABRICATION',
        'Welded': 'FABRICATION',
        'Welded QC': 'READY_TO_SHIP',
        'Paint Start': 'READY_TO_SHIP',
        'Paint complete': 'READY_TO_SHIP',
        'Store at MHMW for shipping': 'READY_TO_SHIP',
        'Shipping planning': 'READY_TO_SHIP',
        'Shipping completed': 'COMPLETE',
        'Complete': 'COMPLETE',
    };

    /**
     * Colors per stage subset for the job log stage dropdown (custom dropdown only).
     */
    const stageGroupColors = {
        FABRICATION: { light: 'rgb(219 234 254)', text: 'rgb(30 64 175)', border: 'rgb(147 197 253)' },
        READY_TO_SHIP: { light: 'rgb(209 250 229)', text: 'rgb(6 95 70)', border: 'rgb(110 231 183)' },
        COMPLETE: { light: 'rgb(237 233 254)', text: 'rgb(91 33 182)', border: 'rgb(196 181 253)' },
    };

    /**
     * Stage options for multiselect (using simplified labels)
     */
    const stageOptions = [
        { value: 'Released', label: 'Released' },
        { value: 'Material Ordered', label: 'Material Ordered' },
        { value: 'Cut start', label: 'Cut start' },
        { value: 'Cut Complete', label: 'Cut comp' },
        { value: 'Fitup Start', label: 'Fitup start' },
        { value: 'Fit Up Complete.', label: 'Fitup comp' },
        { value: 'Weld Start', label: 'Weld start' },
        { value: 'Weld Complete', label: 'Weld comp' },
        { value: 'Welded', label: 'Welded' },
        { value: 'Welded QC', label: 'Welded QC' },
        { value: 'Paint Start', label: 'Paint Start' },
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
        'Cut Complete': {
            unselected: 'bg-blue-100 text-blue-800 border-blue-300',
            selected: 'bg-blue-600 text-white border-blue-700'
        },
        'Fitup Start': {
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
        'Paint Start': {
            unselected: 'bg-blue-100 text-blue-800 border-blue-300',
            selected: 'bg-blue-600 text-white border-blue-700'
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
        'Weld Start': {
            unselected: 'bg-blue-100 text-blue-800 border-blue-300',
            selected: 'bg-blue-600 text-white border-blue-700'
        },
        'Weld Complete': {
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

    const totalFabHrs = useMemo(() =>
        jobs.reduce((sum, job) => sum + (job['Fab Hrs'] || 0) * _getFabModifier(job['Stage'] || ''), 0),
    [jobs]);

    const totalInstallHrs = useMemo(() =>
        jobs.reduce((sum, job) => {
            if (_getFabModifier(job['Stage'] || '') > 0.0) return sum;
            return sum + (job['Install HRS'] || 0) * (1.0 - _parseJobComp(job['Job Comp']));
        }, 0),
    [jobs]);

    /**
     * Reset all filters to default values
     */
    const resetFilters = useCallback(() => {
        setSelectedProjectNames([]);
        setSelectedStages([]);
        setSearch('');
        setSelectedSubset(null);
        localStorage.removeItem('jl_projects');
        localStorage.removeItem('jl_subset');
    }, []);

    return {
        // Filter state
        selectedProjectNames,
        selectedStages,
        search,
        selectedSubset,

        // Filter setters
        setSelectedProjectNames,
        setSelectedStages,
        setSearch,
        setSelectedSubset,

        // Filter options
        projectNameOptions,
        stageOptions,
        stageColors,
        stageToGroup,
        stageGroupColors,

        // Filtered and sorted jobs
        displayJobs,

        // Aggregate KPIs (all jobs, not filtered)
        totalFabHrs,
        totalInstallHrs,

        // Actions
        resetFilters,
        toggleStage,
    };
}