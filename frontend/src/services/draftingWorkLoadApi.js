import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class DraftingWorkLoadApi {
    async fetchData() {
        try {
            const response = await axios.get(
                `${API_BASE_URL}/procore/api/drafting-work-load`
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
            const response = await axios.put(`${API_BASE_URL}/procore/api/drafting-work-load/order`, {
                submittal_id: submittalId,
                order_number: orderNumber
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update order number for submittal ${submittalId}`);
        }
    }

    /**
     * Handle API errors
     */
    _handleError(error, defaultMessage) {
        // Extract the best error message we can find
        const message =
            error.response?.data?.error ||      // Custom API error
            error.response?.data?.details ||    // API details
            error.response?.data?.message ||    // Standard message
            error.message ||                    // JS error message
            defaultMessage;                     // Fallback

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