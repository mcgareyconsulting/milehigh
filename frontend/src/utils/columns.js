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
