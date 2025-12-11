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

            // Debug: Check what we actually received
            console.log('=== RAW RESPONSE DEBUG ===');
            console.log('response.data type:', typeof response.data);
            console.log('response.data is Array?', Array.isArray(response.data));
            console.log('response.data is Object?', typeof response.data === 'object' && response.data !== null && !Array.isArray(response.data));
            console.log('response.data value:', response.data);

            // Debug: Check if response.data is an array (wrong) or object (correct)
            const isArray = Array.isArray(response.data);
            const isObject = !isArray && typeof response.data === 'object' && response.data !== null;

            // Get keys - this is what's showing 147338
            let dataKeys = [];
            if (isArray) {
                dataKeys = Array.from({ length: response.data.length }, (_, i) => String(i));
                console.log('Array length:', response.data.length);
                console.log('First array item:', response.data[0]);
            } else if (isObject) {
                dataKeys = Object.keys(response.data);
                console.log('Object keys:', dataKeys);
                console.log('Object values for keys:', dataKeys.reduce((acc, key) => {
                    acc[key] = typeof response.data[key];
                    return acc;
                }, {}));
            }

            console.log('Jobs API response received:', {
                status: response.status,
                dataType: isArray ? 'array (WRONG!)' : isObject ? 'object (correct)' : typeof response.data,
                dataKeysCount: dataKeys.length,
                dataKeysPreview: dataKeys.slice(0, 10),
                hasJobsKey: isObject && 'jobs' in response.data,
                hasTotalJobsKey: isObject && 'total_jobs' in response.data,
                jobsCount: isObject ? (response.data?.jobs?.length || 0) : 0,
                totalJobs: isObject ? response.data?.total_jobs : undefined
            });
            console.log('=== END RAW RESPONSE DEBUG ===');

            // Handle case where API incorrectly returns array instead of object
            if (isArray) {
                console.error('ERROR: API returned array instead of object! Wrapping in expected format.');
                console.error('Array length:', response.data.length);
                console.error('First array item:', response.data[0]);
                return {
                    total_jobs: response.data.length,
                    jobs: response.data
                };
            }

            // If response.data doesn't have the expected structure, log it
            if (!response.data || !('jobs' in response.data)) {
                console.error('ERROR: Response data missing expected structure!', {
                    hasData: !!response.data,
                    dataType: typeof response.data,
                    dataKeys: response.data ? Object.keys(response.data) : null,
                    dataValue: response.data
                });
            }

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

