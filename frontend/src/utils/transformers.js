/**
 * Transform raw API submittal data to frontend format
 */
import { formatDaysAgo } from './formatters';

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
        'Lifespan': formatDaysAgo(submittal.created_at), // Days since submittal was created
        'Title': submittal.title,
        'Status': submittal.submittal_drafting_status ?? submittal.status,
        'Procore Status': submittal.status, // The actual Procore status field
        'Submittal Drafting Status': submittal.submittal_drafting_status,
        'Type': submittal.type,
        'Ball In Court': submittal.ball_in_court,
        'Last BIC Update': formatDaysAgo(submittal.last_bic_update), // Convert to days ago
        'Order Number': submittal.order_number,
        'Due Date': submittal.due_date,
        'Notes': submittal.notes,
        id: String(rawId)
    };
}

/**
 * Transform array of submittals
 */
export function transformSubmittals(submittals) {
    if (!submittals || !Array.isArray(submittals)) {
        console.warn('transformSubmittals received invalid input:', submittals);
        return [];
    }
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