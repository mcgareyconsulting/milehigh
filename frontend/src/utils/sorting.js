/**
 * Sort submittals by order number, then by ID
 */
export function sortByOrderNumber(submittals) {
    return [...submittals].sort((a, b) => { // ... creates a new array, so we don't mutate the original array
        const orderA = a.order_number ?? a['Order Number'] ?? 999999;
        const orderB = b.order_number ?? b['Order Number'] ?? 999999;

        if (orderA !== orderB) {
            return orderA - orderB;
        }

        return (a['Submittals Id'] || '').localeCompare(b['Submittals Id'] || '');
    });
}

/**
 * Sort submittals by project name alphabetically
 */
export function sortByProjectName(submittals, direction = 'asc') {
    return [...submittals].sort((a, b) => {
        const projectA = (a.project_name ?? a['Project Name'] ?? '').toString().trim();
        const projectB = (b.project_name ?? b['Project Name'] ?? '').toString().trim();

        const comparison = projectA.localeCompare(projectB);
        return direction === 'asc' ? comparison : -comparison;
    });
}

/**
 * Sort submittals by ball in court, then order number
 */
export function sortByBallInCourt(submittals) {
    return [...submittals].sort((a, b) => {
        const ballA = (a.ball_in_court ?? '').toString();
        const ballB = (b.ball_in_court ?? '').toString();

        // Multi-assignee (comma-separated) goes to bottom
        const hasMultipleA = ballA.includes(',');
        const hasMultipleB = ballB.includes(',');

        if (hasMultipleA && !hasMultipleB) return 1;
        if (!hasMultipleA && hasMultipleB) return -1;

        // Sort alphabetically by ball in court
        if (ballA !== ballB) {
            return ballA.localeCompare(ballB);
        }

        // Then by order number
        const orderA = a.order_number ?? a['Order Number'] ?? 999999;
        const orderB = b.order_number ?? b['Order Number'] ?? 999999;
        return orderA - orderB;
    });
}