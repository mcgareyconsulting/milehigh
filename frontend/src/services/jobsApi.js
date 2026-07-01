/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Wraps all job log CRUD, stage/field updates, Gantt data, and archive operations so page components remain free of HTTP logic.
 * exports:
 *   jobsApi: Singleton with methods for fetching, updating, releasing, deleting, archiving, and scheduling jobs,
 *            plus read-only release enrichment (checklist/to-dos, photos, drawings) for the timeline detail modal.
 * imports_from: [axios, ../utils/api]
 * imported_by: [components/PMBoardList.jsx, components/JobsTableRow.jsx, components/GanttChart.jsx, components/ReleaseDetailModal.jsx, pages/PMBoard.jsx, pages/JobLog.jsx, pages/Archive.jsx, hooks/useJobsDataFetching.js, hooks/useArchiveDataFetching.js]
 * invariants:
 *   - Exported as a singleton; all callers share the same instance.
 *   - fetchAllJobs paginates internally and returns the full accumulated array.
 *   - _handleError enriches axios errors with statusCode and originalError before re-throwing.
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

// Configure axios to include credentials for session cookies
axios.defaults.withCredentials = true;

class JobsApi {
    async fetchAllJobs(archived = false) {
        try {
            const allJobs = [];
            let page = 1;
            let hasMore = true;

            // Fetch all pages until we have all the data
            while (hasMore) {
                const response = await axios.get(`${API_BASE_URL}/brain/get-all-jobs`, {
                    // per_page=1000 pulls the whole dataset in one request (the
                    // has_more loop below stays as a safety net for >1000 rows).
                    params: { page, archived, per_page: 1000 }
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

    async fetchData(sinceTimestamp = null, archived = false) {
        try {
            const params = { archived };
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

    async renumberFabricationFabOrders({ dryRun = false } = {}) {
        try {
            const response = await axios.post(
                `${API_BASE_URL}/brain/renumber-fabrication-fab-orders`,
                null,
                { params: { dry_run: dryRun } }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to renumber fabrication fab orders');
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

    async getNotesHistory(job, release, limit = 200) {
        try {
            const response = await axios.get(
                `${API_BASE_URL}/brain/events`,
                { params: { job, release, limit } }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to fetch notes history');
        }
    }

    async updateJobComp(job, release, jobComp) {
        try {
            const response = await axios.patch(
                `${API_BASE_URL}/brain/update-job-comp/${job}/${release}`,
                { job_comp: jobComp }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to update job comp');
        }
    }

    async updateInvoiced(job, release, invoiced) {
        try {
            const response = await axios.patch(
                `${API_BASE_URL}/brain/update-invoiced/${job}/${release}`,
                { invoiced }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to update invoiced');
        }
    }

    async updateStartInstall(job, release, startInstall, installer = undefined, isHardDate = true) {
        try {
            const payload = { is_hard_date: isHardDate };
            // Only send a date when one is provided, so an installer-only change
            // never clears an existing hard date.
            if (startInstall) {
                payload.start_install = startInstall;
            }
            if (installer !== undefined) {
                payload.installer = installer;
            }
            const response = await axios.patch(
                `${API_BASE_URL}/brain/update-start-install/${job}/${release}`,
                payload
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to update start install');
        }
    }

    async getInstallerTeams() {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/installer-teams`);
            return response.data.installer_teams || [];
        } catch (error) {
            throw this._handleError(error, 'Failed to load installer teams');
        }
    }

    // Read-only enrichment for the timeline detail modal. release_id is the Releases PK
    // (the `id` field the get-all-jobs serializer emits), not the job/release pair.
    async getReleaseChecklist(releaseId) {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/releases/${releaseId}/checklist`);
            return response.data; // { release_id, todos, meetings }
        } catch (error) {
            throw this._handleError(error, 'Failed to load release checklist');
        }
    }

    async getReleasePhotos(releaseId) {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/releases/${releaseId}/photos`);
            return response.data.photos || [];
        } catch (error) {
            throw this._handleError(error, 'Failed to load release photos');
        }
    }

    async getReleaseDrawings(releaseId) {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions`);
            return response.data.versions || [];
        } catch (error) {
            throw this._handleError(error, 'Failed to load release drawings');
        }
    }

    async getVersionComments(releaseId, versionId) {
        try {
            const response = await axios.get(
                `${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions/${versionId}/comments`
            );
            return response.data.comments || [];
        } catch (error) {
            throw this._handleError(error, 'Failed to load comments');
        }
    }

    async addVersionComment(releaseId, versionId, body) {
        try {
            const response = await axios.post(
                `${API_BASE_URL}/brain/releases/${releaseId}/drawing/versions/${versionId}/comments`,
                { body }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to add comment');
        }
    }

    async clearStartInstallHardDate(job, release) {
        try {
            const response = await axios.patch(
                `${API_BASE_URL}/brain/update-start-install/${job}/${release}`,
                { clear_hard_date: true }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to clear hard date');
        }
    }

    async setStartInstallAsap(job, release, asap, force = false) {
        try {
            const response = await axios.patch(
                `${API_BASE_URL}/brain/update-start-install/${job}/${release}`,
                { asap, asap_force: force }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, asap ? 'Failed to set ASAP' : 'Failed to clear ASAP');
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

    async getNextReleaseNumber() {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/job-log/release/next-number`);
            return response.data.next_release;
        } catch (error) {
            throw this._handleError(error, 'Failed to fetch next release number');
        }
    }

    /**
     * @deprecated The Gantt/Timeline view is now built on the frontend from the
     * shared releases dataset (see the toBar selector in components/GanttChart.jsx).
     * No caller hits this anymore; it will be removed alongside the
     * /brain/gantt-data route.
     */
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

    async deleteJob(job, release) {
        try {
            const response = await axios.delete(
                `${API_BASE_URL}/brain/jobs/${job}/${release}`
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to delete job');
        }
    }

    async updateJobColumn(job, release, field, value) {
        try {
            const response = await axios.patch(
                `${API_BASE_URL}/brain/jobs/${job}/${release}`,
                { field, value }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to update job column');
        }
    }


    async getArchivePreview() {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/archive-preview`);
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to fetch archive preview');
        }
    }

    async unarchiveRelease(job, release) {
        try {
            const response = await axios.post(`${API_BASE_URL}/brain/unarchive/${job}/${release}`);
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to unarchive release');
        }
    }

    async confirmArchive() {
        try {
            const response = await axios.post(`${API_BASE_URL}/brain/archive-confirm`);
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to archive releases');
        }
    }

    /**
     * Supplier material orders tagged to a release (ordered-but-not-received, etc.)
     */
    async getMaterialOrders(job, release) {
        try {
            const response = await axios.get(
                `${API_BASE_URL}/brain/material-orders`,
                { params: { job, release } }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to fetch material orders');
        }
    }

    /**
     * Mark a material order received (or un-receive with received=false).
     */
    async markMaterialOrderReceived(orderId, received = true) {
        try {
            const response = await axios.post(
                `${API_BASE_URL}/brain/material-orders/${orderId}/received`,
                { received }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to update material order');
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

