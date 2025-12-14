import axios from 'axios';

// Automatically detect dev vs production mode
// Dev mode (npm run dev): Use Flask backend at localhost:8000
// Production mode (npm run build): Use same origin (empty string)
// Can override with VITE_API_URL env var if needed
const API_BASE_URL = import.meta.env.VITE_API_URL ||
    (import.meta.env.DEV ? 'http://localhost:8000' : '');

class JobsApi {
    async fetchData() {
        try {
            const response = await axios.get(
                `${API_BASE_URL}/api/jobs`
            );

            // Log what we get
            console.log('Jobs API response:', response.data);
            console.log('Jobs API response type:', typeof response.data);
            console.log('Jobs Object', response.data.jobs);
            console.log('Jobs Object type:', typeof response.data.jobs);
            // console.log('Jobs Object keys:', Object.keys(response.data.jobs));
            // console.log('Jobs Object length:', response.data.jobs.length);
            // console.log('Jobs Object first item:', response.data.jobs[0]);
            // console.log('Jobs Object first item type:', typeof response.data.jobs[0]);
            // console.log('Jobs Object first item keys:', Object.keys(response.data.jobs[0]));
            // console.log('Jobs Object first item length:', Object.keys(response.data.jobs[0]).length);
            // console.log('Jobs Object first item keys:', Object.keys(response.data.jobs[0]));

            return response.data;
        } catch (error) {
            // Add context and re-throw
            throw this._handleError(error, 'Failed to fetch jobs data');
        }
    }

    async updateStage(job, release, stage) {
        try {
            const response = await axios.patch(
                `${API_BASE_URL}/jobs/${job}/${release}/stage`,
                { stage }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to update stage');
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

