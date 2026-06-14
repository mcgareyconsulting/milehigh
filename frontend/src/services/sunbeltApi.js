/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Wraps the admin Sunbelt rental-report endpoints so the page stays free of HTTP logic.
 * exports:
 *   sunbeltApi: Singleton exposing fetchReport(snapshotId?), fetchSnapshots(), uploadCsv(file, snapshotDate?).
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/RentalReports.jsx]
 * invariants:
 *   - Exported as a singleton; all callers share the same instance.
 *   - _handleError enriches axios errors with statusCode and originalError before re-throwing.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

// Configure axios to include credentials for session cookies
axios.defaults.withCredentials = true;

class SunbeltApi {
    /** Latest (or a specific) reconciled rental snapshot with flags + diff. */
    async fetchReport(snapshotId) {
        try {
            const url = snapshotId
                ? `${API_BASE_URL}/admin/sunbelt/report/${snapshotId}`
                : `${API_BASE_URL}/admin/sunbelt/report`;
            const response = await axios.get(url);
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to load rental report');
        }
    }

    /** Snapshot metadata for the history dropdown (most recent first). */
    async fetchSnapshots() {
        try {
            const response = await axios.get(`${API_BASE_URL}/admin/sunbelt/snapshots`);
            return response.data.snapshots || [];
        } catch (error) {
            throw this._handleError(error, 'Failed to load snapshot history');
        }
    }

    /**
     * Upload a weekly Sunbelt CSV as a new snapshot.
     * @param {File} file - the CSV file
     * @param {string} [snapshotDate] - optional YYYY-MM-DD override (defaults to today)
     */
    async uploadCsv(file, snapshotDate) {
        try {
            const form = new FormData();
            form.append('file', file);
            if (snapshotDate) form.append('snapshot_date', snapshotDate);
            const response = await axios.post(
                `${API_BASE_URL}/admin/sunbelt/upload`,
                form,
                { headers: { 'Content-Type': 'multipart/form-data' } },
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to upload CSV');
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

export const sunbeltApi = new SunbeltApi();
