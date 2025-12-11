import axios from 'axios';

// Use environment variable if set, otherwise use relative URL (works for both dev and production)
// In development with Vite dev server, you can set VITE_API_URL=http://localhost:8000
// In production, if frontend and backend are on same domain, use relative URL (empty string)
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

class JobsApi {
    async fetchData() {
        try {
            const url = `${API_BASE_URL}/api/jobs`;
            console.log('Fetching jobs from:', url);
            const response = await axios.get(url);
            console.log('Jobs API response received:', {
                status: response.status,
                dataKeys: Object.keys(response.data || {}),
                jobsCount: response.data?.jobs?.length || 0
            });
            return response.data;
        } catch (error) {
            console.error('Jobs API error:', {
                url: `${API_BASE_URL}/api/jobs`,
                status: error.response?.status,
                statusText: error.response?.statusText,
                data: error.response?.data
            });
            // Add context and re-throw
            throw this._handleError(error, 'Failed to fetch jobs data');
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
export const jobsApi = new JobsApi();

