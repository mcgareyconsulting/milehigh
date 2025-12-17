/**
 * Sort submittals by order number, then by last_updated for unordered items
 * Ordered items (with order_number) come first, sorted by order number
 * Unordered items (NULL order_number) come after, sorted by last_updated (oldest first = most stale at top)
 */
export function sortByOrderNumber(submittals) {
    return [...submittals].sort((a, b) => {
        const orderA = a.order_number ?? a['Order Number'];
        const orderB = b.order_number ?? b['Order Number'];

        const hasOrderA = orderA !== null && orderA !== undefined && orderA !== '';
        const hasOrderB = orderB !== null && orderB !== undefined && orderB !== '';

        // If one has order and the other doesn't, ordered item comes first
        if (hasOrderA && !hasOrderB) return -1;
        if (!hasOrderA && hasOrderB) return 1;

        // Both have orders - sort by order number
        if (hasOrderA && hasOrderB) {
            const numA = typeof orderA === 'number' ? orderA : parseFloat(orderA);
            const numB = typeof orderB === 'number' ? orderB : parseFloat(orderB);
            if (!isNaN(numA) && !isNaN(numB)) {
                if (numA !== numB) {
                    return numA - numB;
                }
            }
            // If order numbers are equal, sort by ID
            return (a['Submittals Id'] || '').localeCompare(b['Submittals Id'] || '');
        }

        // Both are unordered - sort by last_updated (oldest first = most stale at top)
        const lastUpdatedA = a.last_updated ?? a['Last Updated'];
        const lastUpdatedB = b.last_updated ?? b['Last Updated'];

        if (lastUpdatedA && lastUpdatedB) {
            const dateA = new Date(lastUpdatedA);
            const dateB = new Date(lastUpdatedB);
            if (!isNaN(dateA.getTime()) && !isNaN(dateB.getTime())) {
                // Oldest first (most stale at top)
                return dateA - dateB;
            }
        }

        // Fallback to ID if dates are missing or invalid
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

        // Then by order number (ordered items first, then unordered by last_updated)
        const orderA = a.order_number ?? a['Order Number'];
        const orderB = b.order_number ?? b['Order Number'];

        const hasOrderA = orderA !== null && orderA !== undefined && orderA !== '';
        const hasOrderB = orderB !== null && orderB !== undefined && orderB !== '';

        // If one has order and the other doesn't, ordered item comes first
        if (hasOrderA && !hasOrderB) return -1;
        if (!hasOrderA && hasOrderB) return 1;

        // Both have orders - sort by order number
        if (hasOrderA && hasOrderB) {
            const numA = typeof orderA === 'number' ? orderA : parseFloat(orderA);
            const numB = typeof orderB === 'number' ? orderB : parseFloat(orderB);
            if (!isNaN(numA) && !isNaN(numB)) {
                return numA - numB;
            }
        }

        // Both are unordered - sort by last_updated (oldest first)
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