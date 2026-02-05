/**
 * Default column order for drafting work load
 */
export const DESIRED_COLUMN_ORDER = [
    'Order Number',
    'Project Number',
    'Project Name',
    'Title',
    'Ball In Court',
    'Type',
    'Status',
    'Due Date',
    'Submittal Manager',
    'Last BIC',
    'Creation Date',
    'Notes'
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