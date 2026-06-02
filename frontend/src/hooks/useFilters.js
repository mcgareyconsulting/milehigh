/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Centralizes all DWL filter, search, and column-sort logic so DraftingWorkLoad only handles rendering.
 * exports:
 *   useFilters: Hook returning column-filter state, reachable values, displayRows, and sort/reset handlers for DWL
 * imports_from: [react]
 * imported_by: [../pages/DraftingWorkLoad.jsx]
 * invariants:
 *   - Rows with type 'For Construction' are always excluded before any user filter is applied
 *   - Filtering is per-column (Excel-style): columnFilters maps a display column name to an allowed-value list
 *   - '(Blanks)' is the sentinel for null/empty values; an empty/absent list means "no filter on that column"
 *   - BIC is comma-split: a row matches if ANY of its individual ball-in-court names is allowed
 *   - Default sort groups by BIC then order_number; column sort overrides but preserves multi-assignee-last rule for NAME
 */
import { useState, useMemo, useCallback, useEffect } from 'react';

const ALL_OPTION_VALUE = '__ALL__';
const BLANKS = '(Blanks)';

// Display columns that get an Excel-style header dropdown filter.
const FILTER_COLUMNS = ['PROJ. #', 'NAME', 'TITLE', 'BIC', 'SUB MANAGER', 'PROCORE STATUS'];

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
 * Does a row pass the allowed-value list for one column?
 * - Empty/missing allowed list means no constraint (true).
 * - BIC splits comma-separated names and matches if ANY name is allowed.
 * - '(Blanks)' matches null/empty values.
 */
const rowPassesColumn = (row, col, allowed) => {
    if (!allowed || allowed.length === 0) return true;
    if (col === 'BIC') {
        const raw = (row.ball_in_court ?? row['BIC'] ?? '').toString().trim();
        if (raw === '') return allowed.includes(BLANKS);
        const names = raw.split(',').map((n) => n.trim()).filter(Boolean);
        return names.some((n) => allowed.includes(n));
    }
    const v = getColumnValue(row, col);
    const blank = v === null || v === undefined || String(v).trim() === '';
    return blank ? allowed.includes(BLANKS) : allowed.includes(String(v).trim());
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
    // Per-column dropdown filters: { [displayCol]: string[] of allowed values; '(Blanks)' represents null/empty }
    const [columnFilters, setColumnFiltersState] = useState(() => {
        try {
            const raw = localStorage.getItem('dwl_column_filters');
            return raw ? JSON.parse(raw) : {};
        } catch {
            return {};
        }
    });

    // Text search state
    const [search, setSearch] = useState('');

    // General column sorting: { column: 'TITLE', direction: 'asc' | 'desc' | null }
    const [columnSort, setColumnSort] = useState({ column: null, direction: null });

    // Persist column filters across reloads (drop the key entirely when empty)
    useEffect(() => {
        if (Object.keys(columnFilters).length === 0) {
            localStorage.removeItem('dwl_column_filters');
        } else {
            localStorage.setItem('dwl_column_filters', JSON.stringify(columnFilters));
        }
    }, [columnFilters]);

    const setColumnFilter = useCallback((column, values) => {
        setColumnFiltersState((prev) => {
            const next = { ...prev };
            if (!values || values.length === 0) {
                delete next[column];
            } else {
                next[column] = [...values];
            }
            return next;
        });
    }, []);

    /**
     * Text search across all six filterable columns: project #, project name,
     * title, ball in court, submittal manager, and Procore status.
     */
    const matchesSearch = useCallback((row) => {
        if (search.trim() === '') return true;
        const keywords = search.trim().toLowerCase().split(/\s+/);
        const haystack = [
            String(row.project_number ?? row['PROJ. #'] ?? ''),
            String(row.project_name ?? row['NAME'] ?? ''),
            String(row.title ?? row['TITLE'] ?? ''),
            String(row.ball_in_court ?? row['BIC'] ?? ''),
            String(row.submittal_manager ?? row['SUB MANAGER'] ?? ''),
            String(row.status ?? row['PROCORE STATUS'] ?? ''),
        ].join(' ').toLowerCase();
        return keywords.every((kw) => haystack.includes(kw));
    }, [search]);

    /**
     * Check if a row passes every active per-column dropdown filter.
     */
    const matchesColumnFilters = useCallback((row) => {
        for (const col in columnFilters) {
            if (!rowPassesColumn(row, col, columnFilters[col])) return false;
        }
        return true;
    }, [columnFilters]);

    const matchesSelectedFilter = useCallback(
        (row) => matchesColumnFilters(row) && matchesSearch(row),
        [matchesColumnFilters, matchesSearch]
    );

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
     * Rows after the always-on 'For Construction' exclusion (the base set every
     * filter and reachable-value calculation starts from).
     */
    const baseRows = useMemo(
        () => rows.filter((row) => (row.type ?? row['Type'] ?? '') !== 'For Construction'),
        [rows]
    );

    /**
     * Filtered and sorted rows for display
     */
    const displayRows = useMemo(() => {
        const filtered = baseRows.filter(matchesSelectedFilter);
        return sortRows([...filtered]); // copy to avoid mutating the filtered array
    }, [baseRows, matchesSelectedFilter, sortRows]);

    /**
     * Per-column reachable values: for each filterable column C, the distinct non-blank
     * values present in rows that pass search + every active column filter EXCEPT C's own
     * (Excel-style narrowing). BIC is exploded into individual comma-split names.
     */
    const uniqueValuesByColumn = useMemo(() => {
        const out = {};
        FILTER_COLUMNS.forEach((col) => {
            const set = new Set();
            let hasBlanks = false;
            for (const row of baseRows) {
                if (!matchesSearch(row)) continue;
                let ok = true;
                for (const k in columnFilters) {
                    if (k === col) continue;
                    if (!rowPassesColumn(row, k, columnFilters[k])) {
                        ok = false;
                        break;
                    }
                }
                if (!ok) continue;

                if (col === 'BIC') {
                    const raw = (row.ball_in_court ?? row['BIC'] ?? '').toString().trim();
                    if (raw === '') hasBlanks = true;
                    else raw.split(',').map((n) => n.trim()).filter(Boolean).forEach((n) => set.add(n));
                } else {
                    const v = getColumnValue(row, col);
                    if (v === null || v === undefined || String(v).trim() === '') hasBlanks = true;
                    else set.add(String(v).trim());
                }
            }
            out[col] = {
                values: [...set].sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' })),
                hasBlanks,
            };
        });
        return out;
    }, [baseRows, columnFilters, matchesSearch]);

    /**
     * The lone selected Ball-In-Court drafter, when exactly one non-blank name is
     * checked in the BIC column filter — drives the admin Resort button. Null otherwise.
     */
    const singleSelectedBallInCourt = useMemo(() => {
        const sel = (columnFilters['BIC'] || []).filter((v) => v !== BLANKS);
        return sel.length === 1 ? sel[0] : null;
    }, [columnFilters]);

    /**
     * Reset all filters to default values
     */
    const resetFilters = useCallback(() => {
        setColumnFiltersState({});
        setSearch('');
        setColumnSort({ column: null, direction: null });
    }, []);

    /**
     * Cycle column sort: null -> asc -> desc -> null. Used by the plain (non-dropdown)
     * sortable headers (TITLE, LAST BIC, TYPE, DUE DATE, LIFESPAN, PROJ. #).
     */
    const handleColumnSort = useCallback((column) => {
        setColumnSort((current) => {
            if (current.column === column) {
                if (current.direction === null) return { column, direction: 'asc' };
                if (current.direction === 'asc') return { column, direction: 'desc' };
                return { column: null, direction: null };
            }
            return { column, direction: 'asc' };
        });
    }, []);

    /**
     * Direct sort setter for the column-header dropdowns, which pass an explicit
     * 'asc' | 'desc' | null rather than cycling.
     */
    const setColumnSortDirect = useCallback((column, direction) => {
        if (!direction) setColumnSort({ column: null, direction: null });
        else setColumnSort({ column, direction });
    }, []);

    return {
        // Filter state
        search,
        columnFilters,
        columnSort,

        // Setters / handlers
        setSearch,
        setColumnFilter,
        handleColumnSort,
        setColumnSortDirect,
        resetFilters,

        // Reachable per-column values for the header dropdowns
        uniqueValuesByColumn,

        // Derived
        singleSelectedBallInCourt,

        // Filtered and sorted rows
        displayRows,

        // Constants
        ALL_OPTION_VALUE,
    };
}
