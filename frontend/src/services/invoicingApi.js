/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Wraps the monthly invoicing report endpoint so the report page stays free of HTTP logic.
 * exports:
 *   invoicingApi: Singleton exposing fetchMonthlyReport({ year, month }).
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/InvoicingReport.jsx]
 * invariants:
 *   - Exported as a singleton; all callers share the same instance.
 *   - _handleError enriches axios errors with statusCode and originalError before re-throwing.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

// Configure axios to include credentials for session cookies
axios.defaults.withCredentials = true;

class InvoicingApi {
    /**
     * Fetch the monthly invoicing report grouped by project.
     * @param {{ year?: number, month?: number }} params - 1-based month (1-12).
     */
    async fetchMonthlyReport({ year, month } = {}) {
        try {
            const params = {};
            if (year) params.year = year;
            if (month) params.month = month;
            const response = await axios.get(
                `${API_BASE_URL}/api/reports/monthly-invoicing`,
                { params }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to load invoicing report');
        }
    }

    _handleError(error, defaultMessage) {
        const message =
            error.response?.data?.error ||
            error.response?.data?.message ||
            error.message ||
            defaultMessage;

        const customError = new Error(message);
        customError.originalError = error;
        customError.statusCode = error.response?.status;
        return customError;
    }
}

export const invoicingApi = new InvoicingApi();
