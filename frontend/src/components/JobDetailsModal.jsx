/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Displays a full read-only detail view of a job release in a portal modal with links to events and Procore.
 * exports:
 *   JobDetailsModal: Portal modal showing all fields of a single job/release record
 * imports_from: [react, react-dom, react-router-dom]
 * imported_by: [frontend/src/components/JobsTableRow.jsx]
 * invariants:
 *   - Renders via createPortal to document.body to escape table overflow clipping
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';

import { jobsApi } from '../services/jobsApi';
import { EventsModal } from './EventsModal';

export function JobDetailsModal({ isOpen, onClose, job }) {
    const [eventsOpen, setEventsOpen] = useState(false);
    const [materialOrders, setMaterialOrders] = useState([]);
    const [ordersLoading, setOrdersLoading] = useState(false);

    // Identifiers derived before any early return so the effect's deps are stable.
    const jobId = job ? (job['Job #'] || job.job) : null;
    const relId = job ? (job['Release #'] || job.release) : null;

    useEffect(() => {
        if (!isOpen || jobId == null) return;
        let cancelled = false;
        setOrdersLoading(true);
        jobsApi.getMaterialOrders(jobId, relId)
            .then((data) => { if (!cancelled) setMaterialOrders(data?.orders || []); })
            .catch(() => { if (!cancelled) setMaterialOrders([]); })
            .finally(() => { if (!cancelled) setOrdersLoading(false); });
        return () => { cancelled = true; };
    }, [isOpen, jobId, relId]);

    const handleToggleReceived = async (order) => {
        const next = order.status !== 'received';
        try {
            const data = await jobsApi.markMaterialOrderReceived(order.id, next);
            setMaterialOrders((prev) =>
                prev.map((o) => (o.id === order.id ? (data?.order || o) : o))
            );
        } catch (e) {
            // Leave the row unchanged (e.g. insufficient permissions).
        }
    };

    if (!isOpen || !job) return null;

    const jobNumber = job['Job #'] || job.job;
    const releaseNumber = job['Release #'] || job.release;
    const jobName = job['Job'] || job.job_name || 'N/A';

    const formatDateTime = (dateString) => {
        if (!dateString) return 'N/A';
        try {
            const date = new Date(dateString);
            return date.toLocaleString('en-US', {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: true
            });
        } catch (e) {
            return dateString;
        }
    };

    // Date-only ("2026-06-15") formatter that avoids the UTC-midnight off-by-one
    // a bare new Date(...) would introduce in negative-offset timezones.
    const formatDate = (dateString) => {
        if (!dateString) return '';
        const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(dateString));
        const date = m
            ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
            : new Date(dateString);
        if (isNaN(date)) return dateString;
        return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    };

    const formatTimeAgo = (dateString) => {
        if (!dateString) return 'N/A';
        try {
            const date = new Date(dateString);
            const now = new Date();
            const diffMs = now - date;
            const diffSeconds = Math.floor(diffMs / 1000);
            const diffMinutes = Math.floor(diffSeconds / 60);
            const diffHours = Math.floor(diffMinutes / 60);
            const diffDays = Math.floor(diffHours / 24);

            if (diffDays > 0) {
                return `${diffDays} day${diffDays !== 1 ? 's' : ''}, ${diffHours % 24} hour${(diffHours % 24) !== 1 ? 's' : ''} ago`;
            } else if (diffHours > 0) {
                return `${diffHours} hour${diffHours !== 1 ? 's' : ''}, ${diffMinutes % 60} minute${(diffMinutes % 60) !== 1 ? 's' : ''} ago`;
            } else if (diffMinutes > 0) {
                return `${diffMinutes} minute${diffMinutes !== 1 ? 's' : ''} ago`;
            } else {
                return `${diffSeconds} second${diffSeconds !== 1 ? 's' : ''} ago`;
            }
        } catch (e) {
            return 'N/A';
        }
    };

    const lastUpdatedAt = job.last_updated_at || job['Last Updated At'];
    const sourceOfUpdate = job.source_of_update || job['Source Of Update'];

    const projectId = job.procore_project_id || '';
    const submittalId = job.procore_submittal_id || '';
    const procoreUrl = projectId && submittalId
        ? `https://app.procore.com/webclients/host/companies/18521/projects/${projectId}/tools/submittals/${submittalId}`
        : null;

    const handleEventsClick = () => {
        if (jobNumber && releaseNumber) {
            setEventsOpen(true);
        }
    };

    const modalContent = (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 transition-opacity"
            onClick={onClose}
        >
            <div
                className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-md w-full mx-4 transform transition-all"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xl font-bold text-white">Job Details</h2>
                        <button
                            onClick={onClose}
                            className="text-white hover:text-gray-200 dark:hover:text-slate-200 transition-colors text-2xl font-bold leading-none"
                            aria-label="Close"
                        >
                            ×
                        </button>
                    </div>
                </div>

                <div className="p-6 space-y-4">
                    <div>
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                            {jobName}
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-slate-300">
                            Job: {jobNumber} - Release: {releaseNumber || 'N/A'}
                        </p>
                    </div>

                    <div className="border-t border-gray-200 dark:border-slate-600 pt-4 space-y-4">
                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-sm font-semibold text-gray-700 dark:text-slate-200">Last Updated:</span>
                            </div>
                            {lastUpdatedAt ? (
                                <>
                                    <p className="text-sm text-gray-600 dark:text-slate-300 pl-4 mb-1">
                                        {formatDateTime(lastUpdatedAt)}
                                    </p>
                                    <p className="text-sm text-accent-600 dark:text-accent-400 font-medium pl-4 mb-2">
                                        {formatTimeAgo(lastUpdatedAt)}
                                    </p>
                                    {sourceOfUpdate && (
                                        <p className="text-sm text-gray-500 dark:text-slate-400 pl-4">
                                            Source: <span className="font-medium text-gray-700 dark:text-slate-200">{sourceOfUpdate}</span>
                                        </p>
                                    )}
                                </>
                            ) : (
                                <p className="text-sm text-gray-500 dark:text-slate-400 italic pl-4">
                                    No update information available
                                </p>
                            )}
                        </div>
                    </div>

                    <div className="border-t border-gray-200 dark:border-slate-600 pt-4">
                            <h4 className="text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
                                Materials Ordered
                            </h4>
                            {ordersLoading ? (
                                <p className="text-sm text-gray-500 dark:text-slate-400 italic">Loading…</p>
                            ) : materialOrders.length === 0 ? (
                                <p className="text-sm text-gray-500 dark:text-slate-400 italic">
                                    No materials ordered for this release.
                                </p>
                            ) : (
                                <ul className="space-y-2">
                                    {materialOrders.map((o) => {
                                        // Status orders (galvanizing / stock) track a planning→complete
                                        // shipping lifecycle, not the itemized ordered/received toggle.
                                        const isStatusOrder = Boolean(o.shipping_status);
                                        const received = o.status === 'received';
                                        const complete = o.shipping_status === 'complete';
                                        const badgeLabel = isStatusOrder
                                            ? (complete ? 'Complete' : 'Planning')
                                            : (received ? 'Received' : 'Ordered');
                                        const badgeGreen = isStatusOrder ? complete : received;
                                        const meta = [o.supplier, o.po_number ? `PO ${o.po_number}` : null]
                                            .filter(Boolean).join(' · ');
                                        return (
                                            <li key={o.id} className="border-l-2 border-accent-500 pl-3">
                                                <div className="flex items-center justify-between gap-2">
                                                    <span className={`text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${badgeGreen
                                                        ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
                                                        : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'}`}>
                                                        {badgeLabel}
                                                    </span>
                                                    {!isStatusOrder && (
                                                        <button
                                                            onClick={() => handleToggleReceived(o)}
                                                            className="text-xs text-accent-600 dark:text-accent-400 hover:underline"
                                                        >
                                                            {received ? 'Mark ordered' : 'Mark received'}
                                                        </button>
                                                    )}
                                                </div>
                                                <p className="text-sm text-gray-900 dark:text-slate-100 mt-0.5">
                                                    {o.quantity != null ? `(${o.quantity}) ` : ''}{o.description}
                                                </p>
                                                {meta && (
                                                    <p className="text-xs text-gray-500 dark:text-slate-400">{meta}</p>
                                                )}
                                                {(o.ordered_by || o.ordered_at) && (
                                                    <p className="text-xs text-gray-500 dark:text-slate-400">
                                                        {o.ordered_by ? `Ordered by ${o.ordered_by}` : 'Ordered'}
                                                        {o.ordered_at ? ` · ${formatDate(o.ordered_at)}` : ''}
                                                    </p>
                                                )}
                                                {isStatusOrder && o.ready_at && (
                                                    <p className="text-xs text-gray-500 dark:text-slate-400">
                                                        Ready · {formatDate(o.ready_at)}
                                                    </p>
                                                )}
                                            </li>
                                        );
                                    })}
                                </ul>
                            )}
                    </div>
                </div>

                <div className="bg-gray-50 dark:bg-slate-700 px-6 py-4 rounded-b-xl border-t border-gray-200 dark:border-slate-600 space-y-3">
                    <div className="flex gap-3">
                        {jobNumber && releaseNumber ? (
                            <button
                                onClick={handleEventsClick}
                                className="flex-1 px-4 py-2 bg-accent-600 text-white rounded-lg font-medium hover:bg-accent-700 transition-colors"
                            >
                                Events
                            </button>
                        ) : (
                            <button
                                disabled
                                className="flex-1 px-4 py-2 bg-gray-400 dark:bg-slate-500 text-white rounded-lg font-medium cursor-not-allowed"
                            >
                                Events
                            </button>
                        )}
                        {procoreUrl ? (
                            <a
                                href={procoreUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 transition-colors text-center"
                            >
                                Procore
                            </a>
                        ) : (
                            <button
                                disabled
                                className="flex-1 px-4 py-2 bg-gray-400 dark:bg-slate-500 text-white rounded-lg font-medium cursor-not-allowed"
                            >
                                Procore
                            </button>
                        )}
                        {job.trello_card_id ? (
                            <a
                                href={`https://trello.com/c/${job.trello_card_id}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors text-center"
                            >
                                Trello
                            </a>
                        ) : (
                            <button
                                disabled
                                className="flex-1 px-4 py-2 bg-gray-400 dark:bg-slate-500 text-white rounded-lg font-medium cursor-not-allowed"
                            >
                                Trello
                            </button>
                        )}
                    </div>
                    <button
                        onClick={onClose}
                        className="w-full px-4 py-2 bg-gray-200 dark:bg-slate-600 text-gray-700 dark:text-slate-200 rounded-lg font-medium hover:bg-gray-300 dark:hover:bg-slate-500 transition-colors"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>
    );

    return (
        <>
            {createPortal(modalContent, document.body)}
            <EventsModal
                isOpen={eventsOpen}
                onClose={() => setEventsOpen(false)}
                title={`Events — ${jobNumber}${releaseNumber ? `-${releaseNumber}` : ''}`}
                jobFilter={jobNumber}
                releaseFilter={releaseNumber}
            />
        </>
    );
}

