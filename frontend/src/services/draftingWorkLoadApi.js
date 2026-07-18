/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Provides the frontend API client for the Drafting Work Load view, encapsulating ordering, status, and Procore project management calls.
 * exports:
 *   draftingWorkLoadApi: Singleton instance with methods for fetching, reordering, bumping, and updating DWL submittals.
 * imports_from: [axios, ../utils/api]
 * imported_by: [components/AddProjectModal.jsx, hooks/useDataFetching.js, pages/DraftingWorkLoad.jsx, hooks/useMutations.js, hooks/useDWLDragAndDrop.js]
 * invariants:
 *   - Exported as a singleton; all callers share the same instance.
 *   - _handleError enriches axios errors with statusCode and originalError before re-throwing.
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

// Configure axios to include credentials for session cookies
axios.defaults.withCredentials = true;

class DraftingWorkLoadApi {
    /**
     * Fetch DWL data. Optionally pass { lat, lng } to filter submittals by job_sites containing that point.
     * @param { { lat: number, lng: number } | null } locationFilter - if set, only submittals for matching job_sites are returned
     * @param { 'open' | 'draft' } tab - 'open' = Open status only; 'draft' = status not Open or Closed
     */
    async fetchData(locationFilter = null, tab = 'open') {
        try {
            const params = { tab: (tab === 'draft' || tab === 'all') ? tab : 'open' };
            if (locationFilter && typeof locationFilter.lat === 'number' && typeof locationFilter.lng === 'number') {
                params.lat = locationFilter.lat;
                params.lng = locationFilter.lng;
            }
            const response = await axios.get(
                `${API_BASE_URL}/brain/drafting-work-load`,
                { params }
            );
            return response.data;
        } catch (error) {
            // Add context and re-throw
            throw this._handleError(error, 'Failed to fetch drafting work load data');
        }
    }

    /**
     * Fetch the global Total Fab HRS figure (same number shown on the Job Log).
     * Computed server-side via a single SQL aggregation; returns a float.
     */
    async fetchFabHoursTotal() {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/fab-hours-total`);
            return response.data.total_fab_hrs;
        } catch (error) {
            throw this._handleError(error, 'Failed to fetch total fab hours');
        }
    }

    /**
     * Update order number for a submittal
     */
    async updateOrderNumber(submittalId, orderNumber) {
        try {
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/order`, {
                submittal_id: submittalId,
                order_number: orderNumber
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update order number for submittal ${submittalId}`);
        }
    }

    /**
     * Update notes for a submittal
     */
    async updateNotes(submittalId, notes) {
        try {
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/notes`, {
                submittal_id: submittalId,
                notes: notes
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update notes for submittal ${submittalId}`);
        }
    }

    /**
     * Update submittal drafting status
     */
    async updateStatus(submittalId, status) {
        try {
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/submittal-drafting-status`, {
                submittal_id: submittalId,
                submittal_drafting_status: status
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update status for submittal ${submittalId}`);
        }
    }

    /**
     * Bump a submittal to the 0.9 urgency slot with cascading effects
     */
    async bumpSubmittal(submittalId) {
        try {
            const response = await axios.post(`${API_BASE_URL}/brain/drafting-work-load/bump`, {
                submittal_id: submittalId
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to bump submittal ${submittalId}`);
        }
    }

    /**
     * Fetch submittal statuses for the company (for Procore status dropdown)
     */
    async fetchSubmittalStatuses() {
        try {
            const response = await axios.get(`${API_BASE_URL}/brain/drafting-work-load/submittal-statuses`);
            return response.data.submittal_statuses;
        } catch (error) {
            throw this._handleError(error, 'Failed to fetch submittal statuses');
        }
    }

    /**
     * Update Procore status for a submittal (Draft/Open/Closed/etc.)
     */
    async updateProcoreStatus(submittalId, statusId) {
        try {
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/procore-status`, {
                submittal_id: submittalId,
                status_id: statusId
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update Procore status for submittal ${submittalId}`);
        }
    }

    /**
     * Step a submittal order up or down within its zone (simple swap)
     */
    async stepOrder(submittalId, direction) {
        try {
            const response = await axios.post(`${API_BASE_URL}/brain/drafting-work-load/step`, {
                submittal_id: submittalId,
                direction: direction
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to step submittal ${submittalId} ${direction}`);
        }
    }

    /**
     * Update due date for a submittal, either directly or (Sub-GC submittals only) by
     * backdating 60 business days from a GC jobsite schedule date. The two are mutually
     * exclusive; only pass one.
     */
    async updateDueDate(submittalId, dueDate, gcJobsiteScheduleDate) {
        try {
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/due-date`, {
                submittal_id: submittalId,
                due_date: dueDate,
                gc_jobsite_schedule_date: gcJobsiteScheduleDate,
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update due date for submittal ${submittalId}`);
        }
    }

    /**
     * Set/clear the desired start-install date for a DRR submittal (with an assigned Rel).
     * When setting, due_date is the (possibly drafter-tweaked) Design Drawings Due date; the
     * backend falls back to 15 business days before if it is omitted. Pass start_install null to clear.
     */
    async updateStartInstall(submittalId, startInstall, dueDate) {
        try {
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/start-install`, {
                submittal_id: submittalId,
                start_install: startInstall,
                due_date: dueDate,
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to update start install for submittal ${submittalId}`);
        }
    }

    /**
     * Compress ordered (>= 1) submittals for a drafter to sequential integers
     */
    async resortDrafter(ballInCourt) {
        try {
            const response = await axios.post(`${API_BASE_URL}/brain/drafting-work-load/resort`, {
                ball_in_court: ballInCourt
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to resort submittals for ${ballInCourt}`);
        }
    }

    /**
     * Drag-and-drop reorder submittal
     */
    async dragReorder(submittalId, targetZone, targetOrder, insertBefore = null) {
        try {
            const body = {
                submittal_id: submittalId,
                target_zone: targetZone,
                target_order: targetOrder,
            };
            if (insertBefore !== null) body.insert_before = insertBefore;
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/drag-order`, body);
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to drag reorder submittal ${submittalId}`);
        }
    }

    /**
     * Preview adding a Procore project (no DB writes)
     */
    async previewAddProject(projectId) {
        try {
            const response = await axios.post(`${API_BASE_URL}/admin/procore/add-project/preview`, { project_id: projectId });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to preview project ${projectId}`);
        }
    }

    /**
     * Confirm adding a Procore project (creates webhook + syncs submittals)
     */
    async confirmAddProject(projectId) {
        try {
            const response = await axios.post(`${API_BASE_URL}/admin/procore/add-project/confirm`, { project_id: projectId });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to add project ${projectId}`);
        }
    }

    /**
     * Manually assign (or reassign) a Rel release number to a DRR submittal.
     * @param {string} submittalId
     * @param {number} rel - integer 100-999
     */
    async updateRel(submittalId, rel) {
        try {
            const response = await axios.put(`${API_BASE_URL}/brain/drafting-work-load/rel`, {
                submittal_id: submittalId,
                rel: rel,
            });
            return response.data;
        } catch (error) {
            throw this._handleError(error, `Failed to assign Rel for submittal ${submittalId}`);
        }
    }

    /**
     * Fetch the suggested next available Rel number (to prefill the assign popup).
     * @param {string} [submittalId] - excludes this submittal's own current Rel
     * @returns {Promise<number|null>}
     */
    async fetchNextRel(submittalId) {
        try {
            const params = submittalId ? { submittal_id: submittalId } : {};
            const response = await axios.get(`${API_BASE_URL}/brain/drafting-work-load/rel/next`, { params });
            return response.data.next_rel;
        } catch (error) {
            throw this._handleError(error, 'Failed to fetch suggested Rel');
        }
    }

    /**
     * Pull a submittal's drawing PDF from Procore and (optionally) run a BB compliance
     * review on it. Track B v1 — keyed to the Procore submittal id.
     * @param {string} submittalId - Procore submittal id
     * @param {{ pullOnly?: boolean }} [opts] - pullOnly returns the pulled-file metadata
     *   only (fast); otherwise the review runs inline and can take several minutes.
     */
    async runProcoreBBReview(submittalId, { pullOnly = false, reviewOnly = false, model = null } = {}) {
        try {
            const params = {};
            if (pullOnly) params.pull_only = true;
            if (reviewOnly) params.review_only = true;
            if (model) params.model = model;
            const response = await axios.post(
                `${API_BASE_URL}/brain/procore-submittals/${encodeURIComponent(submittalId)}/bb-review`,
                null,
                {
                    params,
                    timeout: 0, // review can take minutes; don't let axios abort it
                }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'BB review failed');
        }
    }

    /**
     * Whether a drawing for this submittal has already been pulled/cached server-side
     * (so the UI can offer a "Review downloaded" button that skips the Procore pull).
     * @returns {Promise<{cached: boolean, size_bytes: number|null}>}
     */
    async getProcoreBBReviewStatus(submittalId) {
        try {
            const response = await axios.get(
                `${API_BASE_URL}/brain/procore-submittals/${encodeURIComponent(submittalId)}/bb-review`
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to fetch BB review status');
        }
    }

    /**
     * BB review workspace — per-document API (Track B v2).
     * List the drawing documents attached to a Procore submittal, along with each
     * document's download state and any completed BB review summary.
     * @param {string} submittalId - Procore submittal id
     * @returns {Promise<{submittal: object, documents: Array}>}
     */
    async fetchProcoreDocuments(submittalId) {
        try {
            const response = await axios.get(
                `${API_BASE_URL}/brain/procore-submittals/${encodeURIComponent(submittalId)}/documents`
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to load submittal documents');
        }
    }

    /**
     * Pull a single document's PDF from Procore into local storage (may take a few seconds).
     * @param {string} submittalId - Procore submittal id
     * @param {string|number} attachmentId - the document's attachment id
     * @returns {Promise<{ok: boolean, downloaded: boolean, size_bytes: number, name: string, source: string}>}
     */
    async pullProcoreDocument(submittalId, attachmentId) {
        try {
            const response = await axios.post(
                `${API_BASE_URL}/brain/procore-submittals/${encodeURIComponent(submittalId)}/documents/${encodeURIComponent(attachmentId)}/pull`,
                null,
                { timeout: 0 } // the Procore download can take a few seconds
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to pull document from Procore');
        }
    }

    /**
     * Kick off (or re-run) a BB compliance review on a single already-downloaded document.
     * Returns immediately (202) with a pending row; the review runs on a background thread
     * server-side (the Claude call takes minutes) and the caller polls
     * fetchProcoreDocumentReview until status is 'complete' or 'error'.
     * @param {string} submittalId - Procore submittal id
     * @param {string|number} attachmentId - the document's attachment id
     * @param {{ model?: string, reviewOnly?: boolean }} [opts]
     * @returns {Promise<{ok, review_id, status}>}
     */
    async runProcoreDocumentReview(submittalId, attachmentId, { model = null, reviewOnly = true } = {}) {
        try {
            const params = {};
            if (model) params.model = model;
            if (reviewOnly) params.review_only = true;
            const response = await axios.post(
                `${API_BASE_URL}/brain/procore-submittals/${encodeURIComponent(submittalId)}/documents/${encodeURIComponent(attachmentId)}/bb-review`,
                null,
                { params }
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'BB review failed');
        }
    }

    /**
     * Fetch the stored BB review (findings + feedback) for a single document.
     * @param {string} submittalId - Procore submittal id
     * @param {string|number} attachmentId - the document's attachment id
     * @returns {Promise<{review: null | object}>}
     */
    async fetchProcoreDocumentReview(submittalId, attachmentId) {
        try {
            const response = await axios.get(
                `${API_BASE_URL}/brain/procore-submittals/${encodeURIComponent(submittalId)}/documents/${encodeURIComponent(attachmentId)}/bb-review`
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to load document review');
        }
    }

    /**
     * Record accept/reject feedback on a single finding within a document's BB review.
     * @param {string} submittalId - Procore submittal id
     * @param {string|number} attachmentId - the document's attachment id
     * @param {string|number} reviewId - the review id
     * @param {{ finding_index: number, decision: 'accepted'|'rejected', rule_id?: string, notes?: string, finding?: object }} payload
     */
    async saveProcoreDocumentReviewFeedback(submittalId, attachmentId, reviewId, payload) {
        try {
            const response = await axios.post(
                `${API_BASE_URL}/brain/procore-submittals/${encodeURIComponent(submittalId)}/documents/${encodeURIComponent(attachmentId)}/bb-review/${encodeURIComponent(reviewId)}/feedback`,
                payload
            );
            return response.data;
        } catch (error) {
            throw this._handleError(error, 'Failed to save review feedback');
        }
    }

    /**
     * Handle API errors
     */
    _handleError(error, defaultMessage) {
        // Extract the best error message we can find
        const errorMessage =
            error.response?.data?.error ||      // Custom API error
            error.response?.data?.message ||    // Standard message
            error.message ||                    // JS error message
            defaultMessage;                     // Fallback

        // Include details if available (often contains the actual exception)
        const details = error.response?.data?.details;
        const message = details
            ? `${errorMessage}: ${details}`
            : errorMessage;

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