/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Displays a read-only detail modal for a Procore submittal with links to events history and the Procore web UI.
 * exports:
 *   SubmittalDetailsModal: Detail modal for a single submittal record
 * imports_from: [react, react-router-dom]
 * imported_by: []
 * invariants:
 *   - Procore URL is only rendered when both projectId and submittalId are present
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';

export function SubmittalDetailsModal({ isOpen, onClose, submittal }) {
    const navigate = useNavigate();
    
    if (!isOpen || !submittal) return null;

    const submittalId = submittal.submittal_id || submittal['Submittals Id'] || '';
    const projectId = submittal.procore_project_id || submittal['Project Id'] || '';
    const procoreUrl = projectId && submittalId
        ? `https://app.procore.com/webclients/host/companies/18521/projects/${projectId}/tools/submittals/${submittalId}`
        : null;

    const handleEventsClick = () => {
        if (submittalId) {
            // Ensure submittalId is a string (submittal_id is typically numeric but stored as string)
            const submittalIdStr = String(submittalId).trim();
            navigate(`/events?submittal_id=${submittalIdStr}`);
            onClose();
        }
    };

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

    const formatTimeAgo = (seconds) => {
        if (!seconds && seconds !== 0) return 'N/A';
        
        const totalSeconds = Math.floor(seconds);
        const days = Math.floor(totalSeconds / 86400);
        const hours = Math.floor((totalSeconds % 86400) / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const secs = totalSeconds % 60;

        if (days > 0) {
            return `${days} day${days !== 1 ? 's' : ''}, ${hours} hour${hours !== 1 ? 's' : ''} ago`;
        } else if (hours > 0) {
            return `${hours} hour${hours !== 1 ? 's' : ''}, ${minutes} minute${minutes !== 1 ? 's' : ''} ago`;
        } else if (minutes > 0) {
            return `${minutes} minute${minutes !== 1 ? 's' : ''}, ${secs} second${secs !== 1 ? 's' : ''} ago`;
        } else {
            return `${secs} second${secs !== 1 ? 's' : ''} ago`;
        }
    };

    const createdAt = submittal.created_at || submittal['Created At'];
    const lastBallUpdate = submittal.last_ball_in_court_update;
    const timeSinceUpdate = submittal.time_since_ball_in_court_update_seconds;

    return (
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
                        <h2 className="text-xl font-bold text-white">Submittal Details</h2>
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
                            {submittal.title || submittal['Title'] || 'N/A'}
                        </h3>
                        <p className="text-sm text-gray-600 dark:text-slate-300">
                            Submittal ID: {submittal.submittal_id || submittal['Submittals Id'] || 'N/A'}
                        </p>
                    </div>

                    <div className="border-t border-gray-200 dark:border-slate-600 pt-4 space-y-4">
                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-sm font-semibold text-gray-700 dark:text-slate-200">Created At:</span>
                            </div>
                            <p className="text-sm text-gray-600 dark:text-slate-300 pl-4">
                                {formatDateTime(createdAt)}
                            </p>
                        </div>

                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-sm font-semibold text-gray-700 dark:text-slate-200">Last Ball In Court Update:</span>
                            </div>
                            {lastBallUpdate ? (
                                <>
                                    <p className="text-sm text-gray-600 dark:text-slate-300 pl-4 mb-1">
                                        {formatDateTime(lastBallUpdate)}
                                    </p>
                                    <p className="text-sm text-accent-600 dark:text-accent-400 font-medium pl-4">
                                        {formatTimeAgo(timeSinceUpdate)}
                                    </p>
                                </>
                            ) : (
                                <p className="text-sm text-gray-500 dark:text-slate-400 italic pl-4">
                                    No ball in court update recorded
                                </p>
                            )}
                        </div>

                        {submittal.ball_in_court || submittal['Ball In Court'] ? (
                            <div>
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="text-sm font-semibold text-gray-700 dark:text-slate-200">Current Ball In Court:</span>
                                </div>
                                <p className="text-sm text-gray-600 dark:text-slate-300 pl-4">
                                    {submittal.ball_in_court || submittal['Ball In Court']}
                                </p>
                            </div>
                        ) : null}
                    </div>
                </div>

                <div className="bg-gray-50 dark:bg-slate-700 px-6 py-4 rounded-b-xl border-t border-gray-200 dark:border-slate-600 space-y-3">
                    <div className="flex gap-3">
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
                                className="flex-1 px-4 py-2 bg-gray-400 dark:bg-slate-500 text-white rounded-lg font-medium cursor-not-allowed text-center"
                            >
                                Procore
                            </button>
                        )}
                        {submittalId ? (
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
}

