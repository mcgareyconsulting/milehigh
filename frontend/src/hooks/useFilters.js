import { useState, useMemo, useCallback } from 'react';

const ALL_OPTION_VALUE = '__ALL__';

/**
 * Custom hook for managing filters and sorting in DraftingWorkLoad
 * @param {Array} rows - The raw rows/submittals data to filter and sort
 * @returns {Object} Filter state, options, handlers, and filtered/sorted rows
 */
export function useFilters(rows = []) {
    // Filter state
    const [selectedBallInCourt, setSelectedBallInCourt] = useState(ALL_OPTION_VALUE);
    const [selectedSubmittalManager, setSelectedSubmittalManager] = useState(ALL_OPTION_VALUE);
    const [selectedProjectName, setSelectedProjectName] = useState(ALL_OPTION_VALUE);
    const [selectedProcoreStatus, setSelectedProcoreStatus] = useState(ALL_OPTION_VALUE);
    const [projectNameSortMode, setProjectNameSortMode] = useState('normal'); // 'normal', 'a-z', 'z-a'
    const [lifespanSortMode, setLifespanSortMode] = useState('default'); // 'default', 'asc', 'desc'
    const [dueDateSortMode, setDueDateSortMode] = useState('default'); // 'default', 'asc', 'desc'
    const [lastBicUpdateSortMode, setLastBicUpdateSortMode] = useState('default'); // 'default', 'asc', 'desc'

    /**
     * Check if a row matches all selected filters
     */
    const matchesSelectedFilter = useCallback((row) => {
        // Check Ball In Court filter (handles comma-separated values for multiple assignees)
        if (selectedBallInCourt !== ALL_OPTION_VALUE) {
            const ballInCourtValue = (row.ball_in_court ?? '').toString().trim();
            // Check if selected value matches exactly OR appears in comma-separated list
            const ballInCourtNames = ballInCourtValue.split(',').map(name => name.trim());
            if (!ballInCourtNames.includes(selectedBallInCourt)) {
                return false;
            }
        }

        // Check Submittal Manager filter
        if (selectedSubmittalManager !== ALL_OPTION_VALUE) {
            const managerValue = row.submittal_manager ?? row['Submittal Manager'];
            if ((managerValue ?? '').toString().trim() !== selectedSubmittalManager) {
                return false;
            }
        }

        // Check Project Name filter
        if (selectedProjectName !== ALL_OPTION_VALUE) {
            const projectNameValue = row.project_name ?? row['Project Name'];
            if ((projectNameValue ?? '').toString().trim() !== selectedProjectName) {
                return false;
            }
        }

        // Check Procore Status filter
        if (selectedProcoreStatus !== ALL_OPTION_VALUE) {
            const procoreStatusValue = row.status ?? row['Procore Status'];
            if ((procoreStatusValue ?? '').toString().trim() !== selectedProcoreStatus) {
                return false;
            }
        }

        return true;
    }, [selectedBallInCourt, selectedSubmittalManager, selectedProjectName, selectedProcoreStatus]);

    /**
     * Parse a value as date for sorting (returns timestamp or null)
     */
    const getSortableDate = useCallback((row, field) => {
        let raw;
        if (field === 'created_at') {
            raw = row.created_at ?? row['Created At'];
        } else if (field === 'due_date') {
            raw = row.due_date ?? row['Due Date'];
        } else if (field === 'last_bic_update') {
            raw = row.last_bic_update ?? row['Last BIC Update'];
        } else {
            raw = null;
        }
        if (raw == null || raw === '') return null;
        const d = new Date(raw);
        return isNaN(d.getTime()) ? null : d.getTime();
    }, []);

    /**
     * Single comparator: lifespan (if active) -> due date (if active) -> project name / normal.
     * Using one sort() so date sorts are not overwritten by the next sort.
     */
    const sortRows = useCallback((filteredRows) => {
        const arr = [...filteredRows];

        const compareLifespan = (a, b) => {
            const ta = getSortableDate(a, 'created_at');
            const tb = getSortableDate(b, 'created_at');
            const anull = ta == null;
            const bnull = tb == null;
            if (anull && bnull) return 0;
            if (anull) return lifespanSortMode === 'asc' ? 1 : -1;
            if (bnull) return lifespanSortMode === 'asc' ? -1 : 1;
            return lifespanSortMode === 'asc' ? ta - tb : tb - ta;
        };

        const compareDueDate = (a, b) => {
            const ta = getSortableDate(a, 'due_date');
            const tb = getSortableDate(b, 'due_date');
            const anull = ta == null;
            const bnull = tb == null;
            if (anull && bnull) return 0;
            if (anull) return dueDateSortMode === 'asc' ? 1 : -1;
            if (bnull) return dueDateSortMode === 'asc' ? -1 : 1;
            return dueDateSortMode === 'asc' ? ta - tb : tb - ta;
        };

        const compareLastBicUpdate = (a, b) => {
            const ta = getSortableDate(a, 'last_bic_update');
            const tb = getSortableDate(b, 'last_bic_update');
            const anull = ta == null;
            const bnull = tb == null;
            if (anull && bnull) return 0;
            if (anull) return lastBicUpdateSortMode === 'asc' ? 1 : -1;
            if (bnull) return lastBicUpdateSortMode === 'asc' ? -1 : 1;
            return lastBicUpdateSortMode === 'asc' ? ta - tb : tb - ta;
        };

        const compareProjectOrNormal = (a, b) => {
            if (projectNameSortMode === 'a-z') {
                const projectA = (a.project_name ?? a['Project Name'] ?? '').toString().trim();
                const projectB = (b.project_name ?? b['Project Name'] ?? '').toString().trim();
                if (projectA !== projectB) return projectA.localeCompare(projectB);
                const ballA = (a.ball_in_court ?? '').toString();
                const ballB = (b.ball_in_court ?? '').toString();
                const hasMultipleA = ballA.includes(',');
                const hasMultipleB = ballB.includes(',');
                if (hasMultipleA && !hasMultipleB) return 1;
                if (!hasMultipleA && hasMultipleB) return -1;
                if (hasMultipleA && hasMultipleB) return (a['Submittal ID'] || '').localeCompare(b['Submittal ID'] || '');
                const orderA = a.order_number ?? a['Order Number'];
                const orderB = b.order_number ?? b['Order Number'];
                const hasOrderA = orderA !== null && orderA !== undefined && orderA !== '';
                const hasOrderB = orderB !== null && orderB !== undefined && orderB !== '';
                if (hasOrderA && !hasOrderB) return -1;
                if (!hasOrderA && hasOrderB) return 1;
                if (hasOrderA && hasOrderB) {
                    const numA = typeof orderA === 'number' ? orderA : parseFloat(orderA);
                    const numB = typeof orderB === 'number' ? orderB : parseFloat(orderB);
                    if (!isNaN(numA) && !isNaN(numB)) return numA - numB;
                }
                const lastUpdatedA = a.last_updated ?? a['Last Updated'];
                const lastUpdatedB = b.last_updated ?? b['Last Updated'];
                if (lastUpdatedA && lastUpdatedB) {
                    const dateA = new Date(lastUpdatedA);
                    const dateB = new Date(lastUpdatedB);
                    if (!isNaN(dateA.getTime()) && !isNaN(dateB.getTime())) return dateA - dateB;
                }
                return (a['Submittal ID'] || '').localeCompare(b['Submittal ID'] || '');
            }
            if (projectNameSortMode === 'z-a') {
                const projectA = (a.project_name ?? a['Project Name'] ?? '').toString().trim();
                const projectB = (b.project_name ?? b['Project Name'] ?? '').toString().trim();
                if (projectA !== projectB) return projectB.localeCompare(projectA);
                const ballA = (a.ball_in_court ?? '').toString();
                const ballB = (b.ball_in_court ?? '').toString();
                const hasMultipleA = ballA.includes(',');
                const hasMultipleB = ballB.includes(',');
                if (hasMultipleA && !hasMultipleB) return 1;
                if (!hasMultipleA && hasMultipleB) return -1;
                if (hasMultipleA && hasMultipleB) return (a['Submittal ID'] || '').localeCompare(b['Submittal ID'] || '');
                const orderA = a.order_number ?? a['Order Number'];
                const orderB = b.order_number ?? b['Order Number'];
                const hasOrderA = orderA !== null && orderA !== undefined && orderA !== '';
                const hasOrderB = orderB !== null && orderB !== undefined && orderB !== '';
                if (hasOrderA && !hasOrderB) return -1;
                if (!hasOrderA && hasOrderB) return 1;
                if (hasOrderA && hasOrderB) {
                    const numA = typeof orderA === 'number' ? orderA : parseFloat(orderA);
                    const numB = typeof orderB === 'number' ? orderB : parseFloat(orderB);
                    if (!isNaN(numA) && !isNaN(numB)) return numA - numB;
                }
                const lastUpdatedA = a.last_updated ?? a['Last Updated'];
                const lastUpdatedB = b.last_updated ?? b['Last Updated'];
                if (lastUpdatedA && lastUpdatedB) {
                    const dateA = new Date(lastUpdatedA);
                    const dateB = new Date(lastUpdatedB);
                    if (!isNaN(dateA.getTime()) && !isNaN(dateB.getTime())) return dateA - dateB;
                }
                return (a['Submittal ID'] || '').localeCompare(b['Submittal ID'] || '');
            }
            // Normal: Ball In Court, then order_number
            const ballA = (a.ball_in_court ?? '').toString();
            const ballB = (b.ball_in_court ?? '').toString();
            const hasMultipleA = ballA.includes(',');
            const hasMultipleB = ballB.includes(',');
            if (hasMultipleA && !hasMultipleB) return 1;
            if (!hasMultipleA && hasMultipleB) return -1;
            if (hasMultipleA && hasMultipleB) {
                if (ballA !== ballB) return ballA.localeCompare(ballB);
                return (a['Submittal ID'] || '').localeCompare(b['Submittal ID'] || '');
            }
            if (ballA !== ballB) return ballA.localeCompare(ballB);
            const orderA = a.order_number ?? a['Order Number'];
            const orderB = b.order_number ?? b['Order Number'];
            const hasOrderA = orderA !== null && orderA !== undefined && orderA !== '';
            const hasOrderB = orderB !== null && orderB !== undefined && orderB !== '';
            if (hasOrderA && !hasOrderB) return -1;
            if (!hasOrderA && hasOrderB) return 1;
            if (hasOrderA && hasOrderB) {
                const numA = typeof orderA === 'number' ? orderA : parseFloat(orderA);
                const numB = typeof orderB === 'number' ? orderB : parseFloat(orderB);
                if (!isNaN(numA) && !isNaN(numB)) return numA - numB;
            }
            const lastUpdatedA = a.last_updated ?? a['Last Updated'];
            const lastUpdatedB = b.last_updated ?? b['Last Updated'];
            if (lastUpdatedA && lastUpdatedB) {
                const dateA = new Date(lastUpdatedA);
                const dateB = new Date(lastUpdatedB);
                if (!isNaN(dateA.getTime()) && !isNaN(dateB.getTime())) return dateA - dateB;
            }
            return 0;
        };

        arr.sort((a, b) => {
            if (lifespanSortMode !== 'default') {
                const cmp = compareLifespan(a, b);
                if (cmp !== 0) return cmp;
            }
            if (dueDateSortMode !== 'default') {
                const cmp = compareDueDate(a, b);
                if (cmp !== 0) return cmp;
            }
            if (lastBicUpdateSortMode !== 'default') {
                const cmp = compareLastBicUpdate(a, b);
                if (cmp !== 0) return cmp;
            }
            return compareProjectOrNormal(a, b);
        });

        return arr;
    }, [projectNameSortMode, lifespanSortMode, dueDateSortMode, lastBicUpdateSortMode, getSortableDate]);

    /**
     * Filtered and sorted rows for display
     */
    const displayRows = useMemo(() => {
        // First, filter out rows where type is 'For Construction'
        const withoutForConstruction = rows.filter((row) => {
            const type = row.type ?? row['Type'] ?? '';
            return type !== 'For Construction';
        });
        // Then apply user-selected filters
        const filtered = withoutForConstruction.filter(matchesSelectedFilter);
        return sortRows([...filtered]); // Create a copy to avoid mutating the filtered array
    }, [rows, matchesSelectedFilter, sortRows]);

    /**
     * Extract unique ball in court options from rows
     * Handles comma-separated values by extracting individual names
     * Excludes rows where type is 'For Construction'
     */
    const ballInCourtOptions = useMemo(() => {
        const values = new Set();
        rows.forEach((row) => {
            const type = row.type ?? row['Type'] ?? '';
            if (type === 'For Construction') return; // Skip 'For Construction' rows

            const value = row.ball_in_court;
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                // Extract individual names from comma-separated values
                const names = String(value).split(',').map(name => name.trim()).filter(name => name !== '');
                names.forEach(name => values.add(name));
            }
        });
        return Array.from(values).sort((a, b) => a.localeCompare(b));
    }, [rows]);

    /**
     * Extract unique submittal manager options from rows
     * Excludes rows where type is 'For Construction'
     */
    const submittalManagerOptions = useMemo(() => {
        const values = new Set();
        rows.forEach((row) => {
            const type = row.type ?? row['Type'] ?? '';
            if (type === 'For Construction') return; // Skip 'For Construction' rows

            const value = row.submittal_manager ?? row['Submittal Manager'];
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                values.add(String(value).trim());
            }
        });
        return Array.from(values).sort((a, b) => a.localeCompare(b));
    }, [rows]);

    /**
     * Extract unique project name options from rows
     * Excludes rows where type is 'For Construction'
     */
    const projectNameOptions = useMemo(() => {
        const values = new Set();
        rows.forEach((row) => {
            const type = row.type ?? row['Type'] ?? '';
            if (type === 'For Construction') return; // Skip 'For Construction' rows

            const value = row.project_name ?? row['Project Name'];
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                values.add(String(value).trim());
            }
        });
        return Array.from(values).sort((a, b) => a.localeCompare(b));
    }, [rows]);

    /**
     * Extract unique Procore Status options from all rows
     * Excludes rows where type is 'For Construction'
     * Excludes 'Open' and 'Closed' statuses
     */
    const procoreStatusOptions = useMemo(() => {
        const values = new Set();
        rows.forEach((row) => {
            const type = row.type ?? row['Type'] ?? '';
            if (type === 'For Construction') return; // Skip 'For Construction' rows

            const value = row.status ?? row['Procore Status'];
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                const statusValue = String(value).trim();
                // Exclude 'Open' and 'Closed'
                if (statusValue !== 'Open' && statusValue !== 'Closed') {
                    values.add(statusValue);
                }
            }
        });
        return Array.from(values).sort((a, b) => a.localeCompare(b));
    }, [rows]);

    /**
     * Calculate which Procore Status values are available after other filters are applied
     * This is used to disable buttons that have no matching submittals
     */
    const availableProcoreStatuses = useMemo(() => {
        // First, filter out 'For Construction' rows
        const withoutForConstruction = rows.filter((row) => {
            const type = row.type ?? row['Type'] ?? '';
            return type !== 'For Construction';
        });

        // Apply other filters (excluding Procore Status filter itself)
        const filtered = withoutForConstruction.filter((row) => {
            // Check Ball In Court filter
            if (selectedBallInCourt !== ALL_OPTION_VALUE) {
                const ballInCourtValue = (row.ball_in_court ?? '').toString().trim();
                const ballInCourtNames = ballInCourtValue.split(',').map(name => name.trim());
                if (!ballInCourtNames.includes(selectedBallInCourt)) {
                    return false;
                }
            }

            // Check Submittal Manager filter
            if (selectedSubmittalManager !== ALL_OPTION_VALUE) {
                const managerValue = row.submittal_manager ?? row['Submittal Manager'];
                if ((managerValue ?? '').toString().trim() !== selectedSubmittalManager) {
                    return false;
                }
            }

            // Check Project Name filter
            if (selectedProjectName !== ALL_OPTION_VALUE) {
                const projectNameValue = row.project_name ?? row['Project Name'];
                if ((projectNameValue ?? '').toString().trim() !== selectedProjectName) {
                    return false;
                }
            }

            return true;
        });

        // Extract unique Procore Status values from filtered rows (excluding Open and Closed)
        const availableStatuses = new Set();
        filtered.forEach((row) => {
            const value = row.status ?? row['Procore Status'];
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                const statusValue = String(value).trim();
                if (statusValue !== 'Open' && statusValue !== 'Closed') {
                    availableStatuses.add(statusValue);
                }
            }
        });

        return availableStatuses;
    }, [rows, selectedBallInCourt, selectedSubmittalManager, selectedProjectName]);

    /**
     * Reset all filters to default values
     */
    const resetFilters = useCallback(() => {
        setSelectedBallInCourt(ALL_OPTION_VALUE);
        setSelectedSubmittalManager(ALL_OPTION_VALUE);
        setSelectedProjectName(ALL_OPTION_VALUE);
        setSelectedProcoreStatus(ALL_OPTION_VALUE);
        setProjectNameSortMode('normal');
        setLifespanSortMode('default');
        setDueDateSortMode('default');
        setLastBicUpdateSortMode('default');
    }, []);

    /**
     * Toggle project name sort mode: normal -> a-z -> z-a -> normal
     */
    const handleProjectNameSortToggle = useCallback(() => {
        if (projectNameSortMode === 'normal') {
            setProjectNameSortMode('a-z');
        } else if (projectNameSortMode === 'a-z') {
            setProjectNameSortMode('z-a');
        } else {
            setProjectNameSortMode('normal');
        }
    }, [projectNameSortMode]);

    /** Toggle lifespan sort: default -> asc (oldest first) -> desc (newest first) -> default */
    const handleLifespanSortToggle = useCallback(() => {
        setLifespanSortMode((m) => (m === 'default' ? 'asc' : m === 'asc' ? 'desc' : 'default'));
    }, []);

    /** Toggle due date sort: default -> asc (oldest first) -> desc (newest first) -> default */
    const handleDueDateSortToggle = useCallback(() => {
        setDueDateSortMode((m) => (m === 'default' ? 'asc' : m === 'asc' ? 'desc' : 'default'));
    }, []);

    /** Toggle Last BIC Update sort: default -> asc (oldest first) -> desc (newest first) -> default */
    const handleLastBicUpdateSortToggle = useCallback(() => {
        setLastBicUpdateSortMode((m) => (m === 'default' ? 'asc' : m === 'asc' ? 'desc' : 'default'));
    }, []);

    return {
        // Filter state
        selectedBallInCourt,
        selectedSubmittalManager,
        selectedProjectName,
        selectedProcoreStatus,
        projectNameSortMode,
        lifespanSortMode,
        dueDateSortMode,
        lastBicUpdateSortMode,

        // Filter setters
        setSelectedBallInCourt,
        setSelectedSubmittalManager,
        setSelectedProjectName,
        setSelectedProcoreStatus,

        // Filter options
        ballInCourtOptions,
        submittalManagerOptions,
        projectNameOptions,
        procoreStatusOptions,
        availableProcoreStatuses,

        // Filtered and sorted rows
        displayRows,

        // Actions
        resetFilters,
        handleProjectNameSortToggle,
        handleLifespanSortToggle,
        handleDueDateSortToggle,
        handleLastBicUpdateSortToggle,

        // Constants
        ALL_OPTION_VALUE,
    };
}

