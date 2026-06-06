/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Maps snake_case backend submittal fields to uppercase display-name keys expected by the DWL table and PDF export.
 * exports:
 *   transformSubmittals: Transforms an array of raw API submittals to frontend format
 *   getMostRecentUpdate: Finds the latest last_updated timestamp across all submittals
 * imports_from: []
 * imported_by: [hooks/useDataFetching.js]
 * invariants:
 *   - The original snake_case fields are preserved via spread so both naming conventions coexist on each row
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */

/**
 * Transform raw API submittal data to frontend format
 */
function transformSubmittal(submittal, index) {
    const rawId = submittal.submittal_id ?? submittal.id ?? `row-${index}`;

    // Map database field names to frontend display names (case-sensitive)
    return {
        ...submittal,
        'Submittals Id': submittal.submittal_id,
        'Project Id': submittal.procore_project_id,
        'ORDER #': submittal.order_number,
        'Job': submittal.project_number,
        'Rel': submittal.rel,
        'NAME': submittal.project_name,
        'TITLE': submittal.title,
        'PROCORE STATUS': submittal.status,
        'BIC': submittal.ball_in_court,
        'TYPE': submittal.type,
        'COMP. STATUS': submittal.submittal_drafting_status,
        'SUB MANAGER': submittal.submittal_manager,
        'DUE DATE': submittal.due_date,
        'NOTES': submittal.notes,
        id: String(rawId)
    };
}

/**
 * Transform array of submittals
 */
export function transformSubmittals(submittals) {
    return submittals.map((submittal, index) => transformSubmittal(submittal, index));
}

/**
 * Calculate the most recent update timestamp from submittals
 */
export function getMostRecentUpdate(submittals) {
    if (!submittals.length) return null;

    return submittals.reduce((latest, row) => {
        const rowDate = row.last_updated ? new Date(row.last_updated) : null;
        return rowDate && (!latest || rowDate > latest) ? rowDate : latest;
    }, null);
}
