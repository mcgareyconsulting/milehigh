import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

// Configure axios to include credentials for session cookies
axios.defaults.withCredentials = true;

class DraftingWorkLoadApi {
    /**
     * Fetch DWL data. Optionally pass { lat, lng } to filter submittals by job_sites containing that point.
     * @param { { lat: number, lng: number } | null } locationFilter - if set, only submittals for matching job_sites are returned
     * @param { 'open' | 'draft' } tab - 'open' = Open status only; 'draft' = status not Open or Closed
     */
    async fetchData(locationFilter = null, tab = 'open') {
        try {
            const params = { tab: (tab === 'draft' || tab === 'all') ? tab : 'open' };
            if (locationFilter && typeof locationFilter.lat === 'number' && typeof locationFilter.lng === 'number') {
                params.lat = locationFilter.lat;
                params.lng = locationFilter.lng;
            }
            const response = await axios.get(
                `${API_BASE_URL}/brain/drafting-work-load`,
                { params }
            );
            return response.data;
        } catch (error) {
            // Add context and re-throw
            throw this._handleError(error, 'Failed to fetch drafting work load data');
        }
    }

    /**
     * Update order number for a submittal
     */
    async updateOrderNumber(submittalId, orderNumber) {
        try {
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/order`, {
                submittal_id: submittalId,
                order_number: orderNumber
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update order number for submittal ${submittalId}`);
        }
    }

    /**
     * Update notes for a submittal
     */
    async updateNotes(submittalId, notes) {
        try {
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/notes`, {
                submittal_id: submittalId,
                notes: notes
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update notes for submittal ${submittalId}`);
        }
    }

    /**
     * Update submittal drafting status
     */
    async updateStatus(submittalId, status) {
        try {
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/submittal-drafting-status`, {
                submittal_id: submittalId,
                submittal_drafting_status: status
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update status for submittal ${submittalId}`);
        }
    }

    /**
     * Bump a submittal to the 0.9 urgency slot with cascading effects
     */
    async bumpSubmittal(submittalId) {
        try {
            const response = await axios.post(`${API_BASE_URL}/brain/drafting-work-load/bump`, {
                submittal_id: submittalId
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to bump submittal ${submittalId}`);
        }
    }

    /**
     * Fetch submittal statuses for the company (for Procore status dropdown)
     */
    async fetchSubmittalStatuses() {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/drafting-work-load/submittal-statuses`);
            return response.data.submittal_statuses;
        } catch (error) {
            throw this._handleError(error, 'Failed to fetch submittal statuses');
        }
    }

    /**
     * Update Procore status for a submittal (Draft/Open/Closed/etc.)
     */
    async updateProcoreStatus(submittalId, statusId) {
        try {
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/procore-status`, {
                submittal_id: submittalId,
                status_id: statusId
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update Procore status for submittal ${submittalId}`);
        }
    }

    /**
     * Step a submittal order up or down within its zone (simple swap)
     */
    async stepOrder(submittalId, direction) {
        try {
            const response = await axios.post(`${API_BASE_URL}/brain/drafting-work-load/step`, {
                submittal_id: submittalId,
                direction: direction
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to step submittal ${submittalId} ${direction}`);
        }
    }

    /**
     * Update due date for a submittal
     */
    async updateDueDate(submittalId, dueDate) {
        try {
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/due-date`, {
                submittal_id: submittalId,
                due_date: dueDate
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update due date for submittal ${submittalId}`);
        }
    }

    /**
     * Compress ordered (>= 1) submittals for a drafter to sequential integers
     */
    async resortDrafter(ballInCourt) {
        try {
            const response = await axios.post(`${API_BASE_URL}/brain/drafting-work-load/resort`, {
                ball_in_court: ballInCourt
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to resort submittals for ${ballInCourt}`);
        }
    }

    /**
     * Drag-and-drop reorder submittal
     */
    async dragReorder(submittalId, targetZone, targetOrder, insertBefore = null) {
        try {
            const body = {
                submittal_id: submittalId,
                target_zone: targetZone,
                target_order: targetOrder,
            };
            if (insertBefore !== null) body.insert_before = insertBefore;
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/drag-order`, body);
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to drag reorder submittal ${submittalId}`);
        }
    }

    /**
     * Preview adding a Procore project (no DB writes)
     */
    async previewAddProject(projectId) {
        try {
            const response = await axios.post(`${API_BASE_URL}/admin/procore/add-project/preview`, { project_id: projectId });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to preview project ${projectId}`);
        }
    }

    /**
     * Confirm adding a Procore project (creates webhook + syncs submittals)
     */
    async confirmAddProject(projectId) {
        try {
            const response = await axios.post(`${API_BASE_URL}/admin/procore/add-project/confirm`, { project_id: projectId });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to add project ${projectId}`);
        }
    }

    /**
     * Handle API errors
     */
    _handleError(error, defaultMessage) {
        // Extract the best error message we can find
        const errorMessage =
            error.response?.data?.error ||      // Custom API error
            error.response?.data?.message ||    // Standard message
            error.message ||                    // JS error message
            defaultMessage;                     // Fallback

        // Include details if available (often contains the actual exception)
        const details = error.response?.data?.details;
        const message = details
            ? `${errorMessage}: ${details}`
            : errorMessage;

        // Create a new error with the message
        const customError = new Error(message);

        // Preserve original error for debugging
        customError.originalError = error;
        customError.statusCode = error.response?.status;

        return customError;

    }
}

// Singleton instance
export const draftingWorkLoadApi = new DraftingWorkLoadApi();