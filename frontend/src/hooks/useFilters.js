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
    const [projectNameSortMode, setProjectNameSortMode] = useState('normal'); // 'normal', 'a-z', 'z-a'

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

        return true;
    }, [selectedBallInCourt, selectedSubmittalManager, selectedProjectName]);

    /**
     * Sort rows based on projectNameSortMode
     */
    const sortRows = useCallback((filteredRows) => {
        if (projectNameSortMode === 'a-z') {
            return filteredRows.sort((a, b) => {
                const projectA = (a.project_name ?? a['Project Name'] ?? '').toString().trim();
                const projectB = (b.project_name ?? b['Project Name'] ?? '').toString().trim();
                if (projectA !== projectB) {
                    return projectA.localeCompare(projectB);
                }
                // Secondary sort: multi-assignee rows go to bottom within same project
                const ballA = (a.ball_in_court ?? '').toString();
                const ballB = (b.ball_in_court ?? '').toString();
                const hasMultipleA = ballA.includes(',');
                const hasMultipleB = ballB.includes(',');

                // Multi-assignee rows should go to the bottom
                if (hasMultipleA && !hasMultipleB) {
                    return 1; // A goes after B
                }
                if (!hasMultipleA && hasMultipleB) {
                    return -1; // A goes before B
                }

                // If both have multiple or both are single, sort by order_number or submittal_id
                if (hasMultipleA && hasMultipleB) {
                    return (a['Submittals Id'] || '').localeCompare(b['Submittals Id'] || '');
                }

                const orderA = a.order_number ?? a['Order Number'] ?? 999999;
                const orderB = b.order_number ?? b['Order Number'] ?? 999999;
                return orderA - orderB;
            });
        } else if (projectNameSortMode === 'z-a') {
            return filteredRows.sort((a, b) => {
                const projectA = (a.project_name ?? a['Project Name'] ?? '').toString().trim();
                const projectB = (b.project_name ?? b['Project Name'] ?? '').toString().trim();
                if (projectA !== projectB) {
                    return projectB.localeCompare(projectA);
                }
                // Secondary sort: multi-assignee rows go to bottom within same project
                const ballA = (a.ball_in_court ?? '').toString();
                const ballB = (b.ball_in_court ?? '').toString();
                const hasMultipleA = ballA.includes(',');
                const hasMultipleB = ballB.includes(',');

                // Multi-assignee rows should go to the bottom
                if (hasMultipleA && !hasMultipleB) {
                    return 1; // A goes after B
                }
                if (!hasMultipleA && hasMultipleB) {
                    return -1; // A goes before B
                }

                // If both have multiple or both are single, sort by order_number or submittal_id
                if (hasMultipleA && hasMultipleB) {
                    return (a['Submittals Id'] || '').localeCompare(b['Submittals Id'] || '');
                }

                const orderA = a.order_number ?? a['Order Number'] ?? 999999;
                const orderB = b.order_number ?? b['Order Number'] ?? 999999;
                return orderA - orderB;
            });
        } else {
            // Normal sort: by Ball In Court, then by order_number (as float)
            // Multi-assignee cases (comma-separated = reviewers) sort to the bottom
            return filteredRows.sort((a, b) => {
                const ballA = (a.ball_in_court ?? '').toString();
                const ballB = (b.ball_in_court ?? '').toString();

                // Check if either has multiple assignees (comma indicates reviewers)
                const hasMultipleA = ballA.includes(',');
                const hasMultipleB = ballB.includes(',');

                // Multi-assignee rows should go to the bottom
                // If one has multiple and the other doesn't, single assignee comes first
                if (hasMultipleA && !hasMultipleB) {
                    return 1; // A goes after B (A has multiple, B doesn't)
                }
                if (!hasMultipleA && hasMultipleB) {
                    return -1; // A goes before B (A doesn't have multiple, B does)
                }

                // If both have multiple assignees, sort them together alphabetically
                if (hasMultipleA && hasMultipleB) {
                    if (ballA !== ballB) {
                        return ballA.localeCompare(ballB);
                    }
                    // Tiebreaker: sort by submittal_id
                    return (a['Submittals Id'] || '').localeCompare(b['Submittals Id'] || '');
                }

                // Both are single assignees: sort alphabetically by ball_in_court
                if (ballA !== ballB) {
                    return ballA.localeCompare(ballB);
                }

                // Same ball_in_court: sort by order_number as float (nulls last)
                const orderA = a.order_number ?? a['Order Number'] ?? 999999;
                const orderB = b.order_number ?? b['Order Number'] ?? 999999;
                return orderA - orderB;
            });
        }
    }, [projectNameSortMode]);

    /**
     * Filtered and sorted rows for display
     */
    const displayRows = useMemo(() => {
        const filtered = rows.filter(matchesSelectedFilter);
        return sortRows([...filtered]); // Create a copy to avoid mutating the filtered array
    }, [rows, matchesSelectedFilter, sortRows]);

    /**
     * Extract unique ball in court options from rows
     * Handles comma-separated values by extracting individual names
     */
    const ballInCourtOptions = useMemo(() => {
        const values = new Set();
        rows.forEach((row) => {
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
     */
    const submittalManagerOptions = useMemo(() => {
        const values = new Set();
        rows.forEach((row) => {
            const value = row.submittal_manager ?? row['Submittal Manager'];
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                values.add(String(value).trim());
            }
        });
        return Array.from(values).sort((a, b) => a.localeCompare(b));
    }, [rows]);

    /**
     * Extract unique project name options from rows
     */
    const projectNameOptions = useMemo(() => {
        const values = new Set();
        rows.forEach((row) => {
            const value = row.project_name ?? row['Project Name'];
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                values.add(String(value).trim());
            }
        });
        return Array.from(values).sort((a, b) => a.localeCompare(b));
    }, [rows]);

    /**
     * Reset all filters to default values
     */
    const resetFilters = useCallback(() => {
        setSelectedBallInCourt(ALL_OPTION_VALUE);
        setSelectedSubmittalManager(ALL_OPTION_VALUE);
        setSelectedProjectName(ALL_OPTION_VALUE);
        setProjectNameSortMode('normal');
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

    return {
        // Filter state
        selectedBallInCourt,
        selectedSubmittalManager,
        selectedProjectName,
        projectNameSortMode,

        // Filter setters
        setSelectedBallInCourt,
        setSelectedSubmittalManager,
        setSelectedProjectName,

        // Filter options
        ballInCourtOptions,
        submittalManagerOptions,
        projectNameOptions,

        // Filtered and sorted rows
        displayRows,

        // Actions
        resetFilters,
        handleProjectNameSortToggle,

        // Constants
        ALL_OPTION_VALUE,
    };
}

