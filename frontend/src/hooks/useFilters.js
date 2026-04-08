import { useState, useMemo, useCallback } from 'react';

const ALL_OPTION_VALUE = '__ALL__';

/**
 * Get value from row by column name (handles both database field names and display names)
 */
const getColumnValue = (row, column) => {
    // Map display column names to database field names (case-sensitive)
    const columnMap = {
        'ORDER #': 'order_number',
        'PROJ. #': 'project_number',
        'NAME': 'project_name',
        'TITLE': 'title',
        'PROCORE STATUS': 'status',
        'BIC': 'ball_in_court',
        'LAST BIC': 'days_since_ball_in_court_update',
        'TYPE': 'type',
        'COMP. STATUS': 'submittal_drafting_status',
        'SUB MANAGER': 'submittal_manager',
        'DUE DATE': 'due_date',
        'LIFESPAN': 'lifespan',
        'NOTES': 'notes',
    };

    const fieldName = columnMap[column] || column.toLowerCase().replace(/\s+/g, '_');
    
    // Try both the mapped field name and the display column name
    return row[fieldName] ?? row[column] ?? null;
};

/**
 * Compare two values for sorting (handles text, numbers, dates, nulls)
 */
const compareValues = (a, b, direction = 'asc') => {
    // Handle null/undefined values - put them at the end
    if (a == null && b == null) return 0;
    if (a == null) return 1;
    if (b == null) return -1;

    // Try to parse as number
    const numA = typeof a === 'number' ? a : parseFloat(a);
    const numB = typeof b === 'number' ? b : parseFloat(b);
    
    if (!isNaN(numA) && !isNaN(numB)) {
        // Both are numbers
        const result = numA - numB;
        return direction === 'asc' ? result : -result;
    }

    // Try to parse as date
    const dateA = new Date(a);
    const dateB = new Date(b);
    if (!isNaN(dateA.getTime()) && !isNaN(dateB.getTime())) {
        // Both are valid dates
        const result = dateA - dateB;
        return direction === 'asc' ? result : -result;
    }

    // String comparison
    const strA = String(a).trim().toLowerCase();
    const strB = String(b).trim().toLowerCase();
    const result = strA.localeCompare(strB);
    return direction === 'asc' ? result : -result;
};

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
    
    // Text search state
    const [search, setSearch] = useState('');

    // General column sorting: { column: 'Project Name', direction: 'asc' | 'desc' | null }
    // For Project Name, we maintain backward compatibility with the existing 'normal' mode
    const [columnSort, setColumnSort] = useState({ column: null, direction: null });

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
            const managerValue = row.submittal_manager ?? row['SUB MANAGER'];
            if ((managerValue ?? '').toString().trim() !== selectedSubmittalManager) {
                return false;
            }
        }

        // Check Project Name filter
        if (selectedProjectName !== ALL_OPTION_VALUE) {
            const projectNameValue = row.project_name ?? row['NAME'];
            if ((projectNameValue ?? '').toString().trim() !== selectedProjectName) {
                return false;
            }
        }

        // Check Procore Status filter
        if (selectedProcoreStatus !== ALL_OPTION_VALUE) {
            const statusValue = row.status ?? row['PROCORE STATUS'] ?? '';
            if ((statusValue ?? '').toString().trim() !== selectedProcoreStatus) {
                return false;
            }
        }

        // Text search across project name, title, and ball in court
        if (search.trim() !== '') {
            const keywords = search.trim().toLowerCase().split(/\s+/);
            const haystack = [
                String(row.project_name ?? row['NAME'] ?? ''),
                String(row.title ?? row['TITLE'] ?? ''),
                String(row.ball_in_court ?? row['BIC'] ?? ''),
            ].join(' ').toLowerCase();
            if (!keywords.every(kw => haystack.includes(kw))) {
                return false;
            }
        }

        return true;
    }, [selectedBallInCourt, selectedSubmittalManager, selectedProjectName, selectedProcoreStatus, search]);

    /**
     * Sort rows based on columnSort state
     */
    const sortRows = useCallback((filteredRows) => {
        const { column, direction } = columnSort;

        // If no column is being sorted, use default sort (by Ball In Court, then order_number)
        if (!column || !direction) {
            return filteredRows.sort((a, b) => {
                const ballA = (a.ball_in_court ?? '').toString();
                const ballB = (b.ball_in_court ?? '').toString();

                const hasMultipleA = ballA.includes(',');
                const hasMultipleB = ballB.includes(',');

                if (hasMultipleA && !hasMultipleB) return 1;
                if (!hasMultipleA && hasMultipleB) return -1;

                if (hasMultipleA && hasMultipleB) {
                    if (ballA !== ballB) {
                        return ballA.localeCompare(ballB);
                    }
                    return (a['Submittals Id'] || '').localeCompare(b['Submittals Id'] || '');
                }

                if (ballA !== ballB) {
                    return ballA.localeCompare(ballB);
                }

                const orderA = a.order_number ?? a['ORDER #'];
                const orderB = b.order_number ?? b['ORDER #'];

                const hasOrderA = orderA !== null && orderA !== undefined && orderA !== '';
                const hasOrderB = orderB !== null && orderB !== undefined && orderB !== '';

                if (hasOrderA && !hasOrderB) return -1;
                if (!hasOrderA && hasOrderB) return 1;

                if (hasOrderA && hasOrderB) {
                    const numA = typeof orderA === 'number' ? orderA : parseFloat(orderA);
                    const numB = typeof orderB === 'number' ? orderB : parseFloat(orderB);
                    if (!isNaN(numA) && !isNaN(numB)) {
                        return numA - numB;
                    }
                }

                const lastUpdatedA = a.last_updated ?? a['Last Updated'];
                const lastUpdatedB = b.last_updated ?? b['Last Updated'];

                if (lastUpdatedA && lastUpdatedB) {
                    const dateA = new Date(lastUpdatedA);
                    const dateB = new Date(lastUpdatedB);
                    if (!isNaN(dateA.getTime()) && !isNaN(dateB.getTime())) {
                        return dateA - dateB;
                    }
                }

                return 0;
            });
        }

        // Sort by the selected column
        return filteredRows.sort((a, b) => {
            const valueA = getColumnValue(a, column);
            const valueB = getColumnValue(b, column);

            // Primary sort by the selected column
            const comparison = compareValues(valueA, valueB, direction);
            if (comparison !== 0) {
                return comparison;
            }

            // Secondary sort: keep multi-assignee rows at the bottom when sorting by NAME
            if (column === 'NAME') {
                const ballA = (a.ball_in_court ?? '').toString();
                const ballB = (b.ball_in_court ?? '').toString();
                const hasMultipleA = ballA.includes(',');
                const hasMultipleB = ballB.includes(',');

                if (hasMultipleA && !hasMultipleB) return 1;
                if (!hasMultipleA && hasMultipleB) return -1;

                if (hasMultipleA && hasMultipleB) {
                    return (a['Submittals Id'] || '').localeCompare(b['Submittals Id'] || '');
                }

                // For single assignees, sort by order number as secondary
                const orderA = a.order_number ?? a['ORDER #'];
                const orderB = b.order_number ?? b['ORDER #'];
                const hasOrderA = orderA !== null && orderA !== undefined && orderA !== '';
                const hasOrderB = orderB !== null && orderB !== undefined && orderB !== '';

                if (hasOrderA && !hasOrderB) return -1;
                if (!hasOrderA && hasOrderB) return 1;

                if (hasOrderA && hasOrderB) {
                    const numA = typeof orderA === 'number' ? orderA : parseFloat(orderA);
                    const numB = typeof orderB === 'number' ? orderB : parseFloat(orderB);
                    if (!isNaN(numA) && !isNaN(numB)) {
                        return numA - numB;
                    }
                }
            }

            // Default secondary sort: by Submittal ID
            return (a['Submittals Id'] || '').localeCompare(b['Submittals Id'] || '');
        });
    }, [columnSort]);

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
            if (type === 'For Construction') return;

            const value = row.ball_in_court;
            if (value !== null && value !== undefined && String(value).trim() !== '') {
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
            if (type === 'For Construction') return;

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
            if (type === 'For Construction') return;

            const value = row.project_name ?? row['NAME'];
            if (value !== null && value !== undefined && String(value).trim() !== '') {
                values.add(String(value).trim());
            }
        });
        return Array.from(values).sort((a, b) => a.localeCompare(b));
    }, [rows]);

    /**
     * Extract unique Procore status options from rows (subset of statuses present in current data)
     * Excludes rows where type is 'For Construction'
     */
    const procoreStatusOptions = useMemo(() => {
        const values = new Set();
        rows.forEach((row) => {
            const type = row.type ?? row['Type'] ?? '';
            if (type === 'For Construction') return;

            const value = row.status ?? row['PROCORE STATUS'];
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
        setSelectedProcoreStatus(ALL_OPTION_VALUE);
        setSearch('');
        setColumnSort({ column: null, direction: null });
    }, []);

    /**
     * Handle column sort toggle: null -> asc -> desc -> null (cycle)
     */
    const handleColumnSort = useCallback((column) => {
        setColumnSort((current) => {
            // If clicking the same column, cycle: null -> asc -> desc -> null
            if (current.column === column) {
                if (current.direction === null) {
                    return { column, direction: 'asc' };
                } else if (current.direction === 'asc') {
                    return { column, direction: 'desc' };
                } else {
                    return { column: null, direction: null };
                }
            }
            // If clicking a different column, start with asc
            return { column, direction: 'asc' };
        });
    }, []);

    // handleProjectNameSortToggle for NAME column
    // Maps 'normal' -> null, 'a-z' -> asc, 'z-a' -> desc
    const handleProjectNameSortToggle = useCallback(() => {
        handleColumnSort('NAME');
    }, [handleColumnSort]);

    // Get current sort state for NAME column
    const projectNameSortMode = useMemo(() => {
        if (columnSort.column !== 'NAME') return 'normal';
        if (columnSort.direction === 'asc') return 'a-z';
        if (columnSort.direction === 'desc') return 'z-a';
        return 'normal';
    }, [columnSort]);

    return {
        // Filter state
        search,
        selectedBallInCourt,
        selectedSubmittalManager,
        selectedProjectName,
        selectedProcoreStatus,
        columnSort, // New general column sort state
        projectNameSortMode, // Backward compatibility

        // Filter setters
        setSearch,
        setSelectedBallInCourt,
        setSelectedSubmittalManager,
        setSelectedProjectName,
        setSelectedProcoreStatus,

        // Filter options
        ballInCourtOptions,
        submittalManagerOptions,
        projectNameOptions,
        procoreStatusOptions,

        // Filtered and sorted rows
        displayRows,

        // Actions
        resetFilters,
        handleColumnSort, // New general column sort handler
        handleProjectNameSortToggle, // Backward compatibility

        // Constants
        ALL_OPTION_VALUE,
    };
}
