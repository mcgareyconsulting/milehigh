import axios from 'axios';

// Automatically detect dev vs production mode
// Dev mode (npm run dev): Use Flask backend at localhost:8000
// Production mode (npm run build): Use same origin (empty string)
// Can override with VITE_API_URL env var if needed
const API_BASE_URL = import.meta.env.VITE_API_URL ||
    (import.meta.env.DEV ? 'http://localhost:8000' : '');

class DraftingWorkLoadApi {
    async fetchData() {
        try {
            const response = await axios.get(
                `${API_BASE_URL}/brain/drafting-work-load`
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
            const response = await axios.put(`${API_BASE_URL}/procore/api/drafting-work-load/submittal-drafting-status`, {
                submittal_id: submittalId,
                submittal_drafting_status: status
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update status for submittal ${submittalId}`);
        }
    }

    /**
     * Upload Excel file for drafting workload submittals
     */
    async uploadFile(file) {
        // Validate file type
        if (!file.name.toLowerCase().endsWith('.xlsx') && !file.name.toLowerCase().endsWith('.xls')) {
            throw new Error('Please select an Excel file (.xlsx or .xls)');
        }

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await axios.post(
                `${API_BASE_URL}/procore/api/upload/drafting-workload-submittals`,
                formData,
                {
                    headers: {
                        'Content-Type': 'multipart/form-data',
                    },
                }
            );

            if (!response.data.success) {
                throw new Error(response.data.error || 'Upload failed');
            }

            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to upload file');
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