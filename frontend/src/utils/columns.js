/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Defines the canonical column order and visibility logic for the Drafting Work Load table.
 * exports:
 *   DESIRED_COLUMN_ORDER: Ordered array of display-name column headers
 *   getVisibleColumns: Filters DESIRED_COLUMN_ORDER to columns present in the data
 * imports_from: []
 * imported_by: [hooks/useDataFetching.js]
 * invariants:
 *   - Column names are case-sensitive display names matching the backend response keys
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */

/**
 * Default column order for drafting work load (case-sensitive display names)
 */
export const DESIRED_COLUMN_ORDER = [
    'ORDER #',
    'PROJ. #',
    'NAME',
    'TITLE',
    'PROCORE STATUS',
    'BIC',
    'LAST BIC',
    'TYPE',
    'COMP. STATUS',
    'SUB MANAGER',
    'DUE DATE',
    'LIFESPAN',
    'NOTES'
];

/**
 * Determine visible columns from data
 */
export function getVisibleColumns(submittals) {
    const allColumns = submittals[0] ? Object.keys(submittals[0]) : [];

    return DESIRED_COLUMN_ORDER.filter(column =>
        allColumns.includes(column) || submittals.some(row => row[column] !== undefined)
    );
}
