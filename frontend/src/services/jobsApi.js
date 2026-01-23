import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

// Configure axios to include credentials for session cookies
axios.defaults.withCredentials = true;

class JobsApi {
    async fetchAllJobs() {
        try {
            const allJobs = [];
            let page = 1;
            let hasMore = true;

            // Fetch all pages until we have all the data
            while (hasMore) {
                const response = await axios.get(`${API_BASE_URL}/brain/get-all-jobs`, {
                    params: { page }
                });

                // Parse response data if it's a string (sometimes axios doesn't auto-parse)
                let data = response.data;
                if (typeof data === 'string') {
                    data = JSON.parse(data);
                }

                // Add jobs from this page to the accumulated array
                if (data.jobs && Array.isArray(data.jobs)) {
                    allJobs.push(...data.jobs);
                }

                // Check if there are more pages
                if (data.pagination) {
                    hasMore = data.pagination.has_more === true;
                    console.log(`Fetched page ${page}: ${data.jobs?.length || 0} jobs (Total so far: ${allJobs.length}/${data.pagination.total_count})`);
                } else {
                    hasMore = false;
                }

                page++;
            }

            console.log(`Finished fetching all jobs: ${allJobs.length} total`);
            return allJobs;
        } catch (error) {
            // Use the same error handling pattern as fetchData
            throw this._handleError(error, 'Failed to fetch all jobs');
        }
    }

    async fetchData(sinceTimestamp = null) {
        try {
            const params = {};
            if (sinceTimestamp) {
                params.since = sinceTimestamp;
            }

            const response = await axios.get(
                `${API_BASE_URL}/brain/jobs`,
                { params }
            );

            return response.data;
        } catch (error) {
            // Add context and re-throw
            throw this._handleError(error, 'Failed to fetch jobs data');
        }
    }

    async updateStage(job, release, stage) {
        try {
            const response = await axios.patch(
                `${API_BASE_URL}/brain/update-stage/${job}/${release}`,
                { stage }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to update stage');
        }
    }

    async updateFabOrder(job, release, fabOrder) {
        try {
            const response = await axios.patch(
                `${API_BASE_URL}/brain/update-fab-order/${job}/${release}`,
                { fab_order: fabOrder }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to update fab order');
        }
    }

    async updateNotes(job, release, notes) {
        try {
            const response = await axios.patch(
                `${API_BASE_URL}/brain/update-notes/${job}/${release}`,
                { notes }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to update notes');
        }
    }

    async releaseJobData(csvData) {
        try {
            const response = await axios.post(
                `${API_BASE_URL}/brain/job-log/release`,
                { csv_data: csvData }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to release job data');
        }
    }

    async fetchGanttData() {
        try {
            const response = await axios.get(
                `${API_BASE_URL}/brain/gantt-data`
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to fetch Gantt chart data');
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

