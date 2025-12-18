import React, { useState, useEffect } from 'react';
import { AlertMessage } from '../components/AlertMessage';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function DraftingWorkLoadAdmin() {
    const [pin, setPin] = useState('');
    const [authenticated, setAuthenticated] = useState(false);
    const [pinError, setPinError] = useState('');
    const [loading, setLoading] = useState(false);
    const [scanResults, setScanResults] = useState(null);
    const [updating, setUpdating] = useState(false);
    const [updateSuccess, setUpdateSuccess] = useState(false);
    const [updateError, setUpdateError] = useState(null);

    const handlePinSubmit = async (e) => {
        e.preventDefault();
        setPinError('');
        setLoading(true);

        try {
            const url = `${API_BASE_URL}/procore/admin/verify-pin`;
            console.log('Sending PIN verification request to:', url);

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ pin }),
            });

            console.log('Response status:', response.status);
            console.log('Response headers:', Object.fromEntries(response.headers.entries()));

            // Handle response - check if it's valid JSON
            let data;
            const text = await response.text();
            console.log('Response text:', text);

            if (text && text.trim()) {
                try {
                    data = JSON.parse(text);
                } catch (parseError) {
                    console.error('JSON parse error:', parseError, 'Response text:', text);
                    setPinError(`Server error: Invalid response format. Status: ${response.status}`);
                    setLoading(false);
                    return;
                }
            } else {
                // Empty response
                console.warn('Empty response from server');
                if (response.ok) {
                    // Assume success if status is OK but no body
                    setAuthenticated(true);
                    runHealthScan();
                    setLoading(false);
                    return;
                } else {
                    setPinError(`Server error: Empty response. Status: ${response.status}`);
                    setLoading(false);
                    return;
                }
            }

            if (response.ok && data && data.success) {
                setAuthenticated(true);
                // Automatically run scan after authentication
                runHealthScan();
            } else {
                setPinError(data?.error || 'Invalid PIN');
            }
        } catch (error) {
            console.error('PIN verification error:', error);
            setPinError(`Failed to verify PIN: ${error.message}`);
        } finally {
            setLoading(false);
        }
    };

    const runHealthScan = async () => {
        setLoading(true);
        setScanResults(null);
        setUpdateError(null);
        setUpdateSuccess(false);

        try {
            const response = await fetch(`${API_BASE_URL}/procore/health-scan`);
            const data = await response.json();

            if (response.ok) {
                setScanResults(data);
            } else {
                setUpdateError(data.error || 'Failed to run health scan');
            }
        } catch (error) {
            setUpdateError('Failed to run health scan. Please try again.');
            console.error('Health scan error:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleUpdateRecords = async () => {
        if (!scanResults?.differences?.sync_issues?.length) {
            return;
        }

        if (!window.confirm(`Are you sure you want to update ${scanResults.differences.sync_issues.length} submittal records to match API values?`)) {
            return;
        }

        setUpdating(true);
        setUpdateError(null);
        setUpdateSuccess(false);

        try {
            const response = await fetch(`${API_BASE_URL}/procore/health-scan/update`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({}), // Update all sync issues
            });

            const data = await response.json();

            if (response.ok && data.success) {
                setUpdateSuccess(true);
                // Refresh scan results
                setTimeout(() => {
                    runHealthScan();
                }, 1000);
            } else {
                setUpdateError(data.error || 'Failed to update records');
            }
        } catch (error) {
            setUpdateError('Failed to update records. Please try again.');
            console.error('Update error:', error);
        } finally {
            setUpdating(false);
        }
    };

    if (!authenticated) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
                <div className="bg-white rounded-lg shadow-xl p-8 max-w-md w-full">
                    <h1 className="text-3xl font-bold text-gray-800 mb-2">Admin Access</h1>
                    <p className="text-gray-600 mb-6">Enter PIN to access health scan</p>

                    <form onSubmit={handlePinSubmit}>
                        <div className="mb-4">
                            <input
                                type="password"
                                value={pin}
                                onChange={(e) => setPin(e.target.value)}
                                placeholder="Enter PIN"
                                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                required
                                autoFocus
                            />
                            {pinError && (
                                <p className="mt-2 text-sm text-red-600">{pinError}</p>
                            )}
                        </div>
                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                            {loading ? 'Verifying...' : 'Submit'}
                        </button>
                    </form>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 p-6">
            <div className="max-w-7xl mx-auto">
                <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
                    <div className="flex justify-between items-center mb-4">
                        <h1 className="text-3xl font-bold text-gray-800">Health Scan Admin</h1>
                        <div className="flex gap-3">
                            <button
                                onClick={runHealthScan}
                                disabled={loading}
                                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                                {loading ? 'Running Scan...' : 'Run Scan'}
                            </button>
                            <button
                                onClick={() => {
                                    setAuthenticated(false);
                                    setScanResults(null);
                                    setPin('');
                                }}
                                className="px-4 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
                            >
                                Logout
                            </button>
                        </div>
                    </div>

                    {updateSuccess && (
                        <div className="mb-4 p-4 bg-green-100 border border-green-400 text-green-700 rounded-lg">
                            Records updated successfully! Refreshing scan results...
                        </div>
                    )}

                    {updateError && (
                        <div className="mb-4 p-4 bg-red-100 border border-red-400 text-red-700 rounded-lg">
                            {updateError}
                        </div>
                    )}

                    {scanResults && (
                        <div className="space-y-6">
                            {/* Summary */}
                            <div className="bg-gray-50 rounded-lg p-4">
                                <h2 className="text-xl font-semibold text-gray-800 mb-3">Summary</h2>
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                    <div>
                                        <p className="text-sm text-gray-600">Total Orphaned</p>
                                        <p className="text-2xl font-bold text-gray-800">{scanResults.summary.total_orphaned}</p>
                                    </div>
                                    <div>
                                        <p className="text-sm text-gray-600">Sync Issues</p>
                                        <p className="text-2xl font-bold text-orange-600">{scanResults.summary.sync_issues}</p>
                                    </div>
                                    <div>
                                        <p className="text-sm text-gray-600">Deleted/Archived</p>
                                        <p className="text-2xl font-bold text-yellow-600">{scanResults.summary.deleted_submittals}</p>
                                    </div>
                                    <div>
                                        <p className="text-sm text-gray-600">Missing Webhooks</p>
                                        <p className="text-2xl font-bold text-red-600">{scanResults.summary.projects_missing_webhooks}</p>
                                    </div>
                                </div>
                            </div>

                            {/* Sync Issues */}
                            {scanResults.differences.sync_issues.length > 0 && (
                                <div className="bg-white border border-orange-200 rounded-lg p-4">
                                    <div className="flex justify-between items-center mb-4">
                                        <h2 className="text-xl font-semibold text-gray-800">
                                            Sync Issues ({scanResults.differences.sync_issues.length})
                                        </h2>
                                        <button
                                            onClick={handleUpdateRecords}
                                            disabled={updating}
                                            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                        >
                                            {updating ? 'Updating...' : 'Update DB to Match API'}
                                        </button>
                                    </div>
                                    <div className="space-y-4 max-h-96 overflow-y-auto">
                                        {scanResults.differences.sync_issues.map((issue, index) => (
                                            <div key={index} className="border border-gray-200 rounded-lg p-4 bg-gray-50">
                                                <div className="flex justify-between items-start mb-2">
                                                    <div>
                                                        <p className="font-semibold text-gray-800">{issue.title || 'N/A'}</p>
                                                        <p className="text-sm text-gray-600">
                                                            Submittal ID: {issue.submittal_id} | Project: {issue.project_name} ({issue.project_id})
                                                        </p>
                                                    </div>
                                                </div>
                                                <div className="mt-3 space-y-2">
                                                    {issue.ball_in_court.mismatch && (
                                                        <div className="bg-orange-50 border-l-4 border-orange-400 p-3 rounded">
                                                            <p className="text-sm font-semibold text-orange-800">ball_in_court Mismatch:</p>
                                                            <p className="text-sm text-gray-700">
                                                                DB: <span className="font-mono">{issue.ball_in_court.db || 'null'}</span> →
                                                                API: <span className="font-mono font-semibold">{issue.ball_in_court.api || 'null'}</span>
                                                            </p>
                                                        </div>
                                                    )}
                                                    {issue.status.mismatch && (
                                                        <div className="bg-orange-50 border-l-4 border-orange-400 p-3 rounded">
                                                            <p className="text-sm font-semibold text-orange-800">status Mismatch:</p>
                                                            <p className="text-sm text-gray-700">
                                                                DB: <span className="font-mono">{issue.status.db || 'null'}</span> →
                                                                API: <span className="font-mono font-semibold">{issue.status.api || 'null'}</span>
                                                            </p>
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Deleted Submittals */}
                            {scanResults.differences.deleted_submittals.length > 0 && (
                                <div className="bg-white border border-yellow-200 rounded-lg p-4">
                                    <h2 className="text-xl font-semibold text-gray-800 mb-4">
                                        Deleted/Archived Submittals ({scanResults.differences.deleted_submittals.length})
                                    </h2>
                                    <div className="space-y-2 max-h-64 overflow-y-auto">
                                        {scanResults.differences.deleted_submittals.map((deleted, index) => (
                                            <div key={index} className="border border-gray-200 rounded-lg p-3 bg-yellow-50">
                                                <p className="font-semibold text-gray-800">{deleted.title || 'N/A'}</p>
                                                <p className="text-sm text-gray-600">
                                                    Submittal ID: {deleted.submittal_id} | Project: {deleted.project_name} ({deleted.project_id})
                                                </p>
                                                <p className="text-sm text-gray-500 mt-1">
                                                    Last known: status={deleted.db_status}, ball_in_court={deleted.db_ball_in_court}
                                                </p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* API Fetch Errors */}
                            {scanResults.differences.api_fetch_errors.length > 0 && (
                                <div className="bg-white border border-red-200 rounded-lg p-4">
                                    <h2 className="text-xl font-semibold text-gray-800 mb-4">
                                        API Fetch Errors ({scanResults.differences.api_fetch_errors.length})
                                    </h2>
                                    <div className="space-y-2 max-h-64 overflow-y-auto">
                                        {scanResults.differences.api_fetch_errors.map((error, index) => (
                                            <div key={index} className="border border-gray-200 rounded-lg p-3 bg-red-50">
                                                <p className="font-semibold text-gray-800">{error.title || 'N/A'}</p>
                                                <p className="text-sm text-gray-600">
                                                    Submittal ID: {error.submittal_id} | Project: {error.project_name} ({error.project_id})
                                                </p>
                                                <p className="text-sm text-red-600 mt-1">Error: {error.error}</p>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Webhook Status */}
                            {scanResults.webhook_status && scanResults.webhook_status.projects_without_webhooks.length > 0 && (
                                <div className="bg-white border border-red-200 rounded-lg p-4">
                                    <h2 className="text-xl font-semibold text-gray-800 mb-4">
                                        Projects Missing Webhooks ({scanResults.webhook_status.projects_without_webhooks.length})
                                    </h2>
                                    <div className="space-y-1">
                                        {scanResults.webhook_status.projects_without_webhooks.map((projectId, index) => (
                                            <p key={index} className="text-sm text-gray-700">Project {projectId}</p>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {scanResults.summary.total_orphaned === 0 && (
                                <div className="bg-green-50 border border-green-200 rounded-lg p-6 text-center">
                                    <p className="text-lg font-semibold text-green-800">✓ No Issues Found</p>
                                    <p className="text-sm text-green-600 mt-2">All DB submittals are in sync with the API response.</p>
                                </div>
                            )}
                        </div>
                    )}

                    {!scanResults && !loading && (
                        <div className="text-center py-8 text-gray-500">
                            Click "Run Scan" to start the health scan
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

export default DraftingWorkLoadAdmin;
