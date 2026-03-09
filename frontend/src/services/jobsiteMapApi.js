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
