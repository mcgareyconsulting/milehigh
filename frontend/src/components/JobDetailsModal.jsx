import React from 'react';
import { useNavigate } from 'react-router-dom';

export function JobDetailsModal({ isOpen, onClose, job }) {
    const navigate = useNavigate();
    
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

    const handleEventsClick = () => {
        if (jobNumber && releaseNumber) {
            navigate(`/events?job=${jobNumber}&release=${releaseNumber}`);
            onClose();
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 transition-opacity"
            onClick={onClose}
        >
            <div
                className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 transform transition-all"
                onClick={(e) => e.stopPropagation()}
            >
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xl font-bold text-white">Job Details</h2>
                        <button
                            onClick={onClose}
                            className="text-white hover:text-gray-200 transition-colors text-2xl font-bold leading-none"
                            aria-label="Close"
                        >
                            ×
                        </button>
                    </div>
                </div>

                <div className="p-6 space-y-4">
                    <div>
                        <h3 className="text-lg font-semibold text-gray-900 mb-2">
                            {jobName}
                        </h3>
                        <p className="text-sm text-gray-600">
                            Job: {jobNumber} - Release: {releaseNumber || 'N/A'}
                        </p>
                    </div>

                    <div className="border-t border-gray-200 pt-4 space-y-4">
                        <div>
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-sm font-semibold text-gray-700">Last Updated:</span>
                            </div>
                            {lastUpdatedAt ? (
                                <>
                                    <p className="text-sm text-gray-600 pl-4 mb-1">
                                        {formatDateTime(lastUpdatedAt)}
                                    </p>
                                    <p className="text-sm text-accent-600 font-medium pl-4 mb-2">
                                        {formatTimeAgo(lastUpdatedAt)}
                                    </p>
                                    {sourceOfUpdate && (
                                        <p className="text-sm text-gray-500 pl-4">
                                            Source: <span className="font-medium text-gray-700">{sourceOfUpdate}</span>
                                        </p>
                                    )}
                                </>
                            ) : (
                                <p className="text-sm text-gray-500 italic pl-4">
                                    No update information available
                                </p>
                            )}
                        </div>
                    </div>
                </div>

                <div className="bg-gray-50 px-6 py-4 rounded-b-xl border-t border-gray-200 space-y-3">
                    {jobNumber && releaseNumber ? (
                        <button
                            onClick={handleEventsClick}
                            className="w-full px-4 py-2 bg-accent-600 text-white rounded-lg font-medium hover:bg-accent-700 transition-colors"
                        >
                            Events
                        </button>
                    ) : (
                        <button
                            disabled
                            className="w-full px-4 py-2 bg-gray-400 text-white rounded-lg font-medium cursor-not-allowed"
                        >
                            Events
                        </button>
                    )}
                    <button
                        onClick={onClose}
                        className="w-full px-4 py-2 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300 transition-colors"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}

