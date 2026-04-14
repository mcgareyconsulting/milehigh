/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Fetches geofenced job site data for the MapLibre map view so the hook layer stays decoupled from HTTP details.
 * exports:
 *   jobsiteMapApi: Singleton with fetchMapData for retrieving job site map markers and boundaries.
 * imports_from: [axios, ../utils/api]
 * imported_by: [hooks/useJobsiteMap.js]
 * invariants:
 *   - Exported as a singleton; all callers share the same instance.
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

class JobsiteMapApi {
    async fetchMapData() {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/jobsites/map`);
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to fetch jobsite map data');
        }
    }

    _handleError(error, defaultMessage) {
        const errorMessage =
            error.response?.data?.error ||
            error.response?.data?.message ||
            error.message ||
            defaultMessage;
        const details = error.response?.data?.details;
        const message = details ? `${errorMessage}: ${details}` : errorMessage;
        const customError = new Error(message);
        customError.originalError = error;
        customError.statusCode = error.response?.status;
        return customError;
    }
}

export const jobsiteMapApi = new JobsiteMapApi();
