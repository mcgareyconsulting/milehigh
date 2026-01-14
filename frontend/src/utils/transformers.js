/**
 * Transform raw API submittal data to frontend format
 */
function transformSubmittal(submittal, index) {
    const rawId = submittal.submittal_id ?? submittal.id ?? `row-${index}`;

    // Map database field names to frontend expected names
    return {
        ...submittal,
        'Submittals Id': submittal.submittal_id,
        'Project Id': submittal.procore_project_id,
        'Submittal Manager': submittal.submittal_manager,
        'Project Name': submittal.project_name,
        'Project Number': submittal.project_number,
        'Title': submittal.title,
        'Status': submittal.submittal_drafting_status ?? submittal.status,
        'Submittal Drafting Status': submittal.submittal_drafting_status,
        'Type': submittal.type,
        'Ball In Court': submittal.ball_in_court,
        'Order Number': submittal.order_number,
        'Notes': submittal.notes,
        'Created At': submittal.created_at,
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