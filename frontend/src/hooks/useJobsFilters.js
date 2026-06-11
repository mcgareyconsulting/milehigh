/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Centralizes all Job Log filter, subset, and sort logic so JobLog.jsx only handles rendering.
 * exports:
 *   useJobsFilters: Hook returning filter state, stage options/colors, displayJobs, KPI totals, and reset/toggle handlers
 * imports_from: [react]
 * imported_by: [../pages/JobLog.jsx, ../pages/Archive.jsx]
 * invariants:
 *   - selectedProjectNames and selectedSubset are persisted to localStorage across sessions
 *   - Subset views apply stage-group filters then sort by fab_order, EXCEPT
 *     ready_to_ship and paint sort by stage priority (Ship Planning → Store at MHMW →
 *     Paint Complete → Paint Start → Welded QC) then last_updated_at ascending.
 *     paint_fab uses that same stage+date sort for the paint band, then fab_order
 *     for the FABRICATION band.
 *   - totalFabHrs and totalInstallHrs are computed over ALL jobs, not the filtered displayJobs
 * updated_by_agent: 2026-04-28T00:00:00Z
 */
import { useState, useMemo, useCallback, useEffect } from 'react';
import { computeTotalFabHrs } from '../utils/fabHours';

// Stages that make up the Paint department (the `paint` quick-filter set).
const PAINT_STAGES = ['Welded QC', 'Paint Start'];

// Per-stage % of install hours remaining. Mirrors STAGE_HOUR_PERCENTAGES.install
// in app/api/helpers.py — keep in sync. Drives the totalInstallHrs KPI; Job Comp
// no longer factors here (install progress is now stage-driven via Install Start
// and Install Complete transitions).
const _INSTALL_MODIFIER = {
    'Released':         0.0,
    'Material Ordered': 0.0,
    'Cut Start':        0.0,
    'Cut Complete':     0.0,
    'Fitup Start':      0.0,
    'Fitup Complete':   0.0,
    'Weld Start':       1.0,
    'Weld Complete':    1.0,
    'Hold':             1.0,
    'Welded QC':        1.0,
    'Paint Start':      1.0,
    'Paint Complete':   1.0,
    'Store at MHMW':    1.0,
    'Ship Planning':    1.0,
    'Ship Complete':    1.0,
    'Install Start':    0.5,
    'Install Complete': 0.0,
    'Complete':         0.0,
};

function _getInstallModifier(stage) {
    // Unknown stages default to 0 (excluded), mirroring the backend.
    return stage in _INSTALL_MODIFIER ? _INSTALL_MODIFIER[stage] : 0.0;
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

    // Per-column dropdown filters: { [columnName]: string[] of allowed values; '(Blanks)' represents null/empty }
    const [columnFilters, setColumnFiltersState] = useState(() => {
        try {
            const raw = localStorage.getItem('jl_column_filters');
            return raw ? JSON.parse(raw) : {};
        } catch {
            return {};
        }
    });
    // Per-column sort override: { column: string|null, direction: 'asc'|'desc'|null }
    const [columnSort, setColumnSortState] = useState(() => {
        try {
            const raw = localStorage.getItem('jl_column_sort');
            const parsed = raw ? JSON.parse(raw) : null;
            if (parsed && parsed.column && (parsed.direction === 'asc' || parsed.direction === 'desc')) {
                return parsed;
            }
        } catch {
            /* ignore */
        }
        return { column: null, direction: null };
    });

    // Sync filter state to localStorage
    useEffect(() => { localStorage.setItem('jl_projects', JSON.stringify(selectedProjectNames)); }, [selectedProjectNames]);
    useEffect(() => {
        if (selectedSubset === null) {
            localStorage.removeItem('jl_subset');
        } else {
            localStorage.setItem('jl_subset', selectedSubset);
        }
    }, [selectedSubset]);
    useEffect(() => {
        if (Object.keys(columnFilters).length === 0) {
            localStorage.removeItem('jl_column_filters');
        } else {
            localStorage.setItem('jl_column_filters', JSON.stringify(columnFilters));
        }
    }, [columnFilters]);
    useEffect(() => {
        if (!columnSort.column || !columnSort.direction) {
            localStorage.removeItem('jl_column_sort');
        } else {
            localStorage.setItem('jl_column_sort', JSON.stringify(columnSort));
        }
    }, [columnSort]);

    const setColumnFilter = useCallback((column, values) => {
        setColumnFiltersState(prev => {
            const next = { ...prev };
            if (!values || values.length === 0) {
                delete next[column];
            } else {
                next[column] = [...values];
            }
            return next;
        });
    }, []);

    const setColumnSort = useCallback((column, direction) => {
        if (!direction) {
            setColumnSortState({ column: null, direction: null });
        } else {
            setColumnSortState({ column, direction });
        }
    }, []);

    /**
     * Check if a job matches the search string. Search is a loose substring match
     * across Job #, Release #, project name, description, and the dashed
     * Job#-Release# form so users can type '350-567' and still match.
     */
    const matchesSearch = useCallback((job, searchStr) => {
        if (!searchStr || searchStr.trim() === '') return true;
        const keywords = searchStr.trim().toLowerCase().split(/\s+/);
        const jobNum = String(job['Job #'] ?? '');
        const releaseNum = String(job['Release #'] ?? '');
        const haystack = [
            jobNum,
            releaseNum,
            `${jobNum}-${releaseNum}`,
            (job['Job'] || ''),
            (job['Description'] || ''),
        ].join(' ').toLowerCase();
        return keywords.every(kw => haystack.includes(kw));
    }, []);

    /**
     * Check if a job matches the project + stage filters (excluding search).
     */
    const matchesFilters = useCallback((job) => {
        if (selectedProjectNames.length > 0) {
            const jobName = job['Job'] ?? '';
            const normalized = String(jobName).trim();
            if (!selectedProjectNames.includes(normalized)) {
                return false;
            }
        }

        if (selectedStages.length > 0) {
            const jobStage = job['Stage'] ?? '';
            if (!selectedStages.includes(String(jobStage).trim())) {
                return false;
            }
        }

        return true;
    }, [selectedProjectNames, selectedStages]);

    /**
     * Check if a job matches all active per-column dropdown filters.
     * The literal '(Blanks)' in an allowed list matches null/undefined/empty values.
     */
    const matchesColumnFilters = useCallback((job) => {
        for (const col in columnFilters) {
            const allowed = columnFilters[col];
            if (!allowed || allowed.length === 0) continue;
            const v = job[col];
            const isBlank = (v === null || v === undefined || String(v).trim() === '');
            if (isBlank) {
                if (!allowed.includes('(Blanks)')) return false;
            } else {
                if (!allowed.includes(String(v).trim())) return false;
            }
        }
        return true;
    }, [columnFilters]);

    const matchesSelectedFilter = useCallback(
        (job) => matchesFilters(job) && matchesSearch(job, search) && matchesColumnFilters(job),
        [matchesFilters, matchesSearch, search, matchesColumnFilters]
    );

    /**
     * Stage priority for tiebreaking when fab_order values are equal
     * (e.g. all Ready-to-Ship fixed-tier stages share fab_order = 2)
     */
    const STAGE_SORT_PRIORITY = {
        'Ship Planning':  1,
        'Store at MHMW':  2,
        'Paint Complete': 3,
        'Paint Start':    3.5,
        'Welded QC':      4,
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
                // Within the same fab_order (notably the many 80.555 placeholders),
                // cascade chronologically by start_install date ascending so the
                // displayed dates progress in order. Blanks sink to the end.
                const dateA = a['Start install'] ? new Date(a['Start install']) : null;
                const dateB = b['Start install'] ? new Date(b['Start install']) : null;
                if (dateA && dateB && dateA.getTime() !== dateB.getTime()) return dateA - dateB;
                if (dateA && !dateB) return -1;
                if (!dateA && dateB) return 1;
                // Final tiebreak by stage priority within the same fab_order
                const prioA = STAGE_SORT_PRIORITY[a['Stage']] ?? 999;
                const prioB = STAGE_SORT_PRIORITY[b['Stage']] ?? 999;
                return prioA - prioB;
            }
            return String(fabOrderA).localeCompare(String(fabOrderB));
        });
    }, []);

    /**
     * Sort jobs by stage priority (per STAGE_SORT_PRIORITY), then last_updated_at
     * ascending (oldest first). Used by Ready-to-Ship, Paint, and the paint band of
     * Paint+Fab — fab_order is undifferentiated within these stage tiers, so stage
     * groups the rows and recency surfaces the items waiting longest. Unknown stages
     * and rows with null last_updated_at sink to the bottom of their tier.
     */
    const sortByStageThenLastUpdated = useCallback((jobs) => {
        return [...jobs].sort((a, b) => {
            const stageA = String(a['Stage'] ?? '').trim();
            const stageB = String(b['Stage'] ?? '').trim();
            const prioA = STAGE_SORT_PRIORITY[stageA] ?? 999;
            const prioB = STAGE_SORT_PRIORITY[stageB] ?? 999;
            if (prioA !== prioB) return prioA - prioB;

            const rawA = a['last_updated_at'];
            const rawB = b['last_updated_at'];
            const dateA = rawA ? new Date(rawA) : null;
            const dateB = rawB ? new Date(rawB) : null;
            const validA = dateA && !isNaN(dateA.getTime());
            const validB = dateB && !isNaN(dateB.getTime());
            if (!validA && !validB) return 0;
            if (!validA) return 1;
            if (!validB) return -1;
            return dateA.getTime() - dateB.getTime();
        });
    }, []);

    const sortByStageThenFabOrder = useCallback((jobs) => {
        return [...jobs].sort((a, b) => {
            const stageA = String(a['Stage'] ?? '').trim();
            const stageB = String(b['Stage'] ?? '').trim();
            const prioA = STAGE_SORT_PRIORITY[stageA] ?? 999;
            const prioB = STAGE_SORT_PRIORITY[stageB] ?? 999;
            if (prioA !== prioB) return prioA - prioB;

            const numA = a['Fab Order'] == null ? NaN : Number(a['Fab Order']);
            const numB = b['Fab Order'] == null ? NaN : Number(b['Fab Order']);
            const hasA = !isNaN(numA);
            const hasB = !isNaN(numB);
            if (hasA && hasB && numA !== numB) return numA - numB;
            if (hasA !== hasB) return hasA ? -1 : 1;

            const dateA = a['last_updated_at'] ? new Date(a['last_updated_at']) : null;
            const dateB = b['last_updated_at'] ? new Date(b['last_updated_at']) : null;
            const validA = dateA && !isNaN(dateA.getTime());
            const validB = dateB && !isNaN(dateB.getTime());
            if (!validA && !validB) return 0;
            if (!validA) return 1;
            if (!validB) return -1;
            return dateA.getTime() - dateB.getTime();
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
     * Numeric columns get numeric comparison (with nulls always sorted to the end).
     * All other columns compare via locale-aware string compare with numeric collation.
     */
    const NUMERIC_COLUMNS = useMemo(() => new Set(['Job #', 'Fab Order', 'Fab Hrs', 'Install HRS']), []);

    // Date-valued columns compare chronologically (asc = oldest first).
    const DATE_COLUMNS = useMemo(() => new Set(['Released', 'Start install', 'Comp. ETA']), []);

    const compareByColumn = useCallback((a, b, column, direction) => {
        const va = a?.[column];
        const vb = b?.[column];
        const aBlank = (va === null || va === undefined || String(va).trim() === '');
        const bBlank = (vb === null || vb === undefined || String(vb).trim() === '');
        // Blanks always sort to the end, regardless of direction
        if (aBlank && bBlank) return 0;
        if (aBlank) return 1;
        if (bBlank) return -1;
        let cmp;
        if (DATE_COLUMNS.has(column)) {
            const ta = new Date(va).getTime();
            const tb = new Date(vb).getTime();
            const validA = !isNaN(ta);
            const validB = !isNaN(tb);
            // Unparseable dates sink to the end like blanks
            if (!validA && !validB) return 0;
            if (!validA) return 1;
            if (!validB) return -1;
            cmp = ta - tb;
        } else if (NUMERIC_COLUMNS.has(column)) {
            const na = Number(va);
            const nb = Number(vb);
            if (!isNaN(na) && !isNaN(nb)) {
                cmp = na - nb;
            } else {
                cmp = String(va).localeCompare(String(vb), undefined, { numeric: true });
            }
        } else {
            cmp = String(va).localeCompare(String(vb), undefined, { numeric: true, sensitivity: 'base' });
        }
        return direction === 'desc' ? -cmp : cmp;
    }, [NUMERIC_COLUMNS, DATE_COLUMNS]);

    /**
     * Base-filtered jobs (project name, job #, release #, etc.) before any subset
     * narrowing. Shared by displayJobs and the ASAP-propagation memo.
     */
    const baseFiltered = useMemo(() => jobs.filter(matchesSelectedFilter), [jobs, matchesSelectedFilter]);

    /**
     * Apply the active quick-filter subset (Job Order / Ready to Ship / Paint /
     * Paint+Fab / Fab) to an already-filtered base list, returning the subset's
     * membership + canonical ordering. Pure of column-header filters and column
     * sort — those are layered on top by displayJobs only. Shared by displayJobs
     * (table) and boardJobs (PM Board), so both honor the same subset semantics.
     */
    const selectSubset = useCallback((base) => {
        if (!selectedSubset) {
            return sortJobs([...base]);
        } else if (selectedSubset === 'job_order') {
            return getJobOrderSubset(base);
        } else if (selectedSubset === 'ready_to_ship') {
            const readyToShipStages = ['Ship Planning', 'Store at MHMW', 'Paint Complete'];
            const rtsOnly = base.filter(job => readyToShipStages.includes(String(job['Stage'] ?? '').trim()));
            return sortByStageThenLastUpdated(rtsOnly);
        } else if (selectedSubset === 'paint') {
            const paintOnly = base.filter(job => PAINT_STAGES.includes(String(job['Stage'] ?? '').trim()));
            return sortByStageThenFabOrder(paintOnly);
        } else if (selectedSubset === 'paint_fab') {
            const paintStages = ['Paint Complete', ...PAINT_STAGES];
            const paintOnly = base.filter(job => paintStages.includes(String(job['Stage'] ?? '').trim()));
            const paintSorted = sortByStageThenFabOrder(paintOnly);
            const fabOnly = base.filter(job => String(job['Stage Group'] ?? '').trim() === 'FABRICATION');
            const fabSorted = sortByFabOrder(fabOnly);
            return [...paintSorted, ...fabSorted];
        } else if (selectedSubset === 'fab') {
            return getFabSubset(base);
        }
        return [...base];
    }, [selectedSubset, sortJobs, getJobOrderSubset, getFabSubset, sortByFabOrder, sortByStageThenLastUpdated, sortByStageThenFabOrder]);

    /**
     * Filtered and sorted jobs for display based on selected subset
     */
    const displayJobs = useMemo(() => {
        let result = selectSubset(baseFiltered);

        // Column sort overrides default/subset ordering when active
        if (columnSort.column && columnSort.direction) {
            result = [...result].sort((a, b) => compareByColumn(a, b, columnSort.column, columnSort.direction));
        }

        return result;
    }, [baseFiltered, selectSubset, columnSort, compareByColumn]);

    /**
     * PM Board list: narrowed by the toolbar controls ONLY — project + stage +
     * search + the quick-filter subset — but NOT the per-column header dropdowns
     * (matchesColumnFilters) or the column sort. The board groups/sorts internally,
     * so only membership matters here.
     */
    const baseFilteredToolbar = useMemo(
        () => jobs.filter(job => matchesFilters(job) && matchesSearch(job, search)),
        [jobs, matchesFilters, matchesSearch, search]
    );
    const boardJobs = useMemo(() => selectSubset(baseFilteredToolbar), [selectSubset, baseFilteredToolbar]);

    /**
     * Out-of-department ASAP releases to surface at the bottom of the Paint and
     * Ready-to-Ship filters, so a downstream foreman can see hot releases still moving
     * through an earlier department. Kept separate from displayJobs (the canonical
     * in-filter list used for counts, CSV, and PDF) so these reference rows never
     * inflate those. Tagged with _asapPropagated/_asapOrigin for the renderers; their
     * stages never overlap the in-filter stages, so no de-duplication is needed.
     */
    const propagatedAsapJobs = useMemo(() => {
        if (selectedSubset !== 'paint' && selectedSubset !== 'ready_to_ship') return [];

        // Fab ASAPs surface in both Paint and Ready-to-Ship.
        const fab = baseFiltered
            .filter(job => String(job['Stage Group'] ?? '').trim() === 'FABRICATION' && job['start_install_asap'] === true)
            .map(job => ({ ...job, _asapPropagated: true, _asapOrigin: 'Fab' }));

        // Paint ASAPs additionally surface in Ready-to-Ship.
        const paint = selectedSubset === 'ready_to_ship'
            ? baseFiltered
                .filter(job => PAINT_STAGES.includes(String(job['Stage'] ?? '').trim()) && job['start_install_asap'] === true)
                .map(job => ({ ...job, _asapPropagated: true, _asapOrigin: 'Paint' }))
            : [];

        return sortByFabOrder([...fab, ...paint]);
    }, [baseFiltered, selectedSubset, sortByFabOrder]);

    /**
     * Secondary search: jobs matching the search with all project/stage/subset
     * filters bypassed. Empty unless the primary displayJobs is empty and the
     * user has entered a search term — surfaces matches hidden by active filters.
     */
    const secondarySearchResults = useMemo(() => {
        if (search.trim() === '' || displayJobs.length > 0) return [];
        const matched = jobs.filter(job => matchesSearch(job, search));
        return sortJobs([...matched]);
    }, [jobs, search, displayJobs, matchesSearch, sortJobs]);

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
     * Project options for the standalone Projects dropdown: { number, name } pairs,
     * one per unique project name (a name that spans multiple job numbers keeps the
     * lowest number as its representative — rare). Sorted by job number ascending.
     * The committed filter value remains the name, so it plugs into matchesFilters /
     * selectedProjectNames unchanged.
     */
    const projectOptions = useMemo(() => {
        const byName = new Map();
        jobs.forEach((job) => {
            const name = job['Job'];
            if (name === null || name === undefined || String(name).trim() === '') return;
            const trimmedName = String(name).trim();
            const num = Number(job['Job #']);
            const existing = byName.get(trimmedName);
            if (!existing || (!isNaN(num) && num < existing.numberValue)) {
                byName.set(trimmedName, {
                    name: trimmedName,
                    number: job['Job #'] ?? '',
                    numberValue: isNaN(num) ? Infinity : num,
                });
            }
        });
        return Array.from(byName.values())
            .sort((a, b) => a.numberValue - b.numberValue)
            .map(({ name, number }) => ({ name, number }));
    }, [jobs]);

    /**
     * Stage → stage_group for subset-based dropdown colors (matches backend).
     * FABRICATION = Fab, READY_TO_SHIP = Ready to Ship, COMPLETE = Complete.
     */
    const stageToGroup = {
        'Released':         'FABRICATION',
        'Material Ordered': 'FABRICATION',
        'Cut Start':        'FABRICATION',
        'Cut Complete':     'FABRICATION',
        'Fitup Start':      'FABRICATION',
        'Fitup Complete':   'FABRICATION',
        'Weld Start':       'FABRICATION',
        'Weld Complete':    'FABRICATION',
        'Hold':             'FABRICATION',
        'Welded QC':        'READY_TO_SHIP',
        'Paint Start':      'READY_TO_SHIP',
        'Paint Complete':   'READY_TO_SHIP',
        'Store at MHMW':    'READY_TO_SHIP',
        'Ship Planning':    'READY_TO_SHIP',
        'Ship Complete':    'COMPLETE',
        'Install Start':    'COMPLETE',
        'Install Complete': 'COMPLETE',
        'Complete':         'COMPLETE',
    };

    /**
     * Colors per stage subset for the job log stage dropdown (custom dropdown only).
     */
    const stageGroupColors = {
        FABRICATION: { light: 'rgb(219 234 254)', text: 'rgb(30 64 175)', border: 'rgb(147 197 253)' },
        READY_TO_SHIP: { light: 'rgb(209 250 229)', text: 'rgb(6 95 70)', border: 'rgb(110 231 183)' },
        COMPLETE: { light: 'rgb(237 233 254)', text: 'rgb(91 33 182)', border: 'rgb(196 181 253)' },
    };

    // Background color applied to a Fab Order cell when its value duplicates another
    // fab_order *within the same stage group*. Per-group so dups in fabrication and
    // ready-to-ship are visually distinguishable.
    const stageGroupDupColors = {
        FABRICATION: '#f97316',
        READY_TO_SHIP: '#2563eb',
        COMPLETE: '#7c3aed',
    };

    /**
     * Stage options for multiselect (using simplified labels)
     */
    const stageOptions = [
        { value: 'Released', label: 'Released' },
        { value: 'Material Ordered', label: 'Material Ordered' },
        { value: 'Cut Start', label: 'Cut Start' },
        { value: 'Cut Complete', label: 'Cut comp' },
        { value: 'Fitup Start', label: 'Fitup start' },
        { value: 'Fitup Complete', label: 'Fitup comp' },
        { value: 'Weld Start', label: 'Weld start' },
        { value: 'Weld Complete', label: 'Weld comp' },
        { value: 'Welded QC', label: 'Welded QC' },
        { value: 'Paint Start', label: 'Paint Start' },
        { value: 'Paint Complete', label: 'Paint comp' },
        { value: 'Hold', label: 'Hold' },
        { value: 'Store at MHMW', label: 'Store' },
        { value: 'Ship Planning', label: 'Ship plan' },
        { value: 'Ship Complete', label: 'Ship comp' },
        { value: 'Install Start', label: 'Install start' },
        { value: 'Install Complete', label: 'Install comp' },
        { value: 'Complete', label: 'Complete' }
    ];

    /**
     * Color mapping for each stage (matching dropdown colors)
     * Unselected: lighter background, selected: darker background with white text
     */
    const _BLUE = {
        unselected: 'bg-blue-100 text-blue-800 border-blue-300',
        selected: 'bg-blue-600 text-white border-blue-700'
    };
    const _EMERALD = {
        unselected: 'bg-emerald-100 text-emerald-800 border-emerald-300',
        selected: 'bg-emerald-600 text-white border-emerald-700'
    };
    const _VIOLET = {
        unselected: 'bg-violet-100 text-violet-800 border-violet-300',
        selected: 'bg-violet-600 text-white border-violet-700'
    };
    const _YELLOW = {
        unselected: 'bg-yellow-100 text-yellow-800 border-yellow-300',
        selected: 'bg-yellow-600 text-white border-yellow-700'
    };
    const stageColors = {
        'Released':         _BLUE,
        'Material Ordered': _BLUE,
        'Cut Start':        _BLUE,
        'Cut Complete':     _BLUE,
        'Fitup Start':      _BLUE,
        'Fitup Complete':   _BLUE,
        'Weld Start':       _BLUE,
        'Weld Complete':    _BLUE,
        'Hold':             _BLUE,
        'Welded QC':        _YELLOW,
        'Paint Start':      _BLUE,
        'Paint Complete':   _EMERALD,
        'Store at MHMW':    _EMERALD,
        'Ship Planning':    _EMERALD,
        'Ship Complete':    _VIOLET,
        'Install Start':    _VIOLET,
        'Install Complete': _VIOLET,
        'Complete':         _VIOLET,
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

    const totalFabHrs = useMemo(() => computeTotalFabHrs(jobs), [jobs]);

    // Stage-driven install hour total. Each stage carries an install %
    // (Install Start = 50%, Install Complete = 0%, etc.) per the matrix in
    // app/api/helpers.py STAGE_HOUR_PERCENTAGES. Job Comp is no longer a
    // factor — it's still used for completion gating and the install-prog
    // review sort, but not for this KPI.
    const totalInstallHrs = useMemo(() =>
        jobs.reduce((sum, job) => {
            const modifier = _getInstallModifier(job['Stage'] || '');
            if (modifier === 0.0) return sum;
            return sum + (job['Install HRS'] || 0) * modifier;
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
        setColumnFiltersState({});
        setColumnSortState({ column: null, direction: null });
        localStorage.removeItem('jl_projects');
        localStorage.removeItem('jl_subset');
        localStorage.removeItem('jl_column_filters');
        localStorage.removeItem('jl_column_sort');
    }, []);

    return {
        // Filter state
        selectedProjectNames,
        selectedStages,
        search,
        selectedSubset,
        columnFilters,
        columnSort,

        // Filter setters
        setSelectedProjectNames,
        setSelectedStages,
        setSearch,
        setSelectedSubset,
        setColumnFilter,
        setColumnSort,

        // Filter options
        projectNameOptions,
        projectOptions,
        stageOptions,
        stageColors,
        stageToGroup,
        stageGroupColors,
        stageGroupDupColors,

        // Filter predicates (exposed so callers can compute reachable values)
        matchesFilters,
        matchesSearch,

        // Filtered and sorted jobs
        displayJobs,
        boardJobs,
        propagatedAsapJobs,
        secondarySearchResults,

        // Aggregate KPIs (all jobs, not filtered)
        totalFabHrs,
        totalInstallHrs,

        // Actions
        resetFilters,
        toggleStage,
    };
}