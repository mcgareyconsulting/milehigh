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
        'PROJ. #': submittal.project_number,
        'NAME': submittal.project_name,
        'TITLE': submittal.title,
        'PROCORE STATUS': submittal.status,
        'BIC': submittal.ball_in_court,
        'LAST BIC': submittal.days_since_ball_in_court_update,
        'TYPE': submittal.type,
        'COMP. STATUS': submittal.submittal_drafting_status,
        'SUB MANAGER': submittal.submittal_manager,
        'DUE DATE': submittal.due_date,
        'LIFESPAN': submittal.lifespan,
        'NOTES': submittal.notes,
        // Include ball_in_court tracking fields
        last_ball_in_court_update: submittal.last_ball_in_court_update,
        time_since_ball_in_court_update_seconds: submittal.time_since_ball_in_court_update_seconds,
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
