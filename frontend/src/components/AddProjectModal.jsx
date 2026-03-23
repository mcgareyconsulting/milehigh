import React, { useState } from 'react';
import { draftingWorkLoadApi } from '../services/draftingWorkLoadApi';

export function AddProjectModal({ isOpen, onClose }) {
    const [step, setStep] = useState('input');
    const [projectId, setProjectId] = useState('');
    const [loading, setLoading] = useState(false);
    const [previewData, setPreviewData] = useState(null);
    const [confirmData, setConfirmData] = useState(null);
    const [errorMessage, setErrorMessage] = useState(null);

    if (!isOpen) return null;

    const resetAndClose = () => {
        setStep('input');
        setProjectId('');
        setLoading(false);
        setPreviewData(null);
        setConfirmData(null);
        setErrorMessage(null);
        onClose();
    };

    const isValidId = projectId.trim() !== '' && !isNaN(parseInt(projectId.trim(), 10));

    const handlePreview = async () => {
        setLoading(true);
        setErrorMessage(null);
        try {
            const data = await draftingWorkLoadApi.previewAddProject(parseInt(projectId.trim(), 10));
            setPreviewData(data);
            setStep('preview');
        } catch (err) {
            setErrorMessage(err.message);
            setStep('error');
        } finally {
            setLoading(false);
        }
    };

    const handleConfirm = async () => {
        setLoading(true);
        setErrorMessage(null);
        try {
            const data = await draftingWorkLoadApi.confirmAddProject(parseInt(projectId.trim(), 10));
            setConfirmData(data);
            setStep('success');
        } catch (err) {
            setErrorMessage(err.message);
            setStep('error');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 transition-opacity"
            onClick={resetAndClose}
        >
            <div
                className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-lg w-full mx-4 transform transition-all"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xl font-bold text-white">Add Procore Project</h2>
                        <button
                            onClick={resetAndClose}
                            className="text-white hover:text-gray-200 transition-colors text-2xl font-bold leading-none"
                            aria-label="Close"
                        >
                            ×
                        </button>
                    </div>
                </div>

                {/* Body */}
                <div className="p-6">
                    {step === 'input' && (
                        <div className="space-y-4">
                            <p className="text-sm text-gray-600 dark:text-slate-300">
                                Enter a Procore project ID to create webhooks and sync submittals to the database.
                            </p>
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 dark:text-slate-200 mb-1">
                                    Procore Project ID
                                </label>
                                <input
                                    type="text"
                                    value={projectId}
                                    onChange={(e) => setProjectId(e.target.value)}
                                    onKeyDown={(e) => { if (e.key === 'Enter' && isValidId && !loading) handlePreview(); }}
                                    placeholder="e.g. 123456"
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-accent-500"
                                    autoFocus
                                />
                            </div>
                            <div className="flex justify-end gap-3 pt-2">
                                <button
                                    onClick={resetAndClose}
                                    className="px-4 py-2 rounded-lg font-medium text-gray-700 dark:text-slate-200 bg-gray-100 dark:bg-slate-700 hover:bg-gray-200 dark:hover:bg-slate-600 transition-all"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handlePreview}
                                    disabled={!isValidId || loading}
                                    className={`px-4 py-2 rounded-lg font-medium transition-all ${
                                        !isValidId || loading
                                            ? 'bg-gray-300 dark:bg-slate-600 text-gray-500 dark:text-slate-400 cursor-not-allowed'
                                            : 'bg-accent-600 text-white hover:bg-accent-700 cursor-pointer'
                                    }`}
                                >
                                    {loading ? 'Loading\u2026' : 'Preview'}
                                </button>
                            </div>
                        </div>
                    )}

                    {step === 'preview' && previewData && (
                        <div className="space-y-4">
                            <div>
                                <p className="text-lg font-semibold text-gray-900 dark:text-white">
                                    {previewData.project_name || `Project ${previewData.project_id}`}
                                </p>
                                {previewData.project_number && (
                                    <p className="text-sm text-gray-500 dark:text-slate-400">#{previewData.project_number}</p>
                                )}
                            </div>

                            <div className="border-t border-gray-200 dark:border-slate-600 pt-4">
                                <p className="text-sm font-semibold text-gray-700 dark:text-slate-200 mb-1">Webhook URL</p>
                                <p className="text-xs font-mono text-gray-600 dark:text-slate-300 break-all bg-gray-50 dark:bg-slate-700 rounded px-2 py-1">
                                    {previewData.webhook_url}
                                </p>
                            </div>

                            <div className="border-t border-gray-200 dark:border-slate-600 pt-4">
                                <p className="text-sm font-semibold text-gray-700 dark:text-slate-200 mb-2">
                                    Submittals to sync ({previewData.total} total)
                                </p>
                                <table className="w-full text-sm">
                                    <tbody>
                                        {Object.entries(previewData.submittal_counts).map(([status, count]) => (
                                            <tr key={status} className="border-b border-gray-100 dark:border-slate-700">
                                                <td className="py-1 text-gray-700 dark:text-slate-300">{status}</td>
                                                <td className="py-1 text-right font-medium text-gray-900 dark:text-white">{count}</td>
                                            </tr>
                                        ))}
                                        <tr>
                                            <td className="py-1 font-semibold text-gray-900 dark:text-white">Total</td>
                                            <td className="py-1 text-right font-semibold text-gray-900 dark:text-white">{previewData.total}</td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>

                            <div className="flex justify-end gap-3 pt-2">
                                <button
                                    onClick={() => setStep('input')}
                                    disabled={loading}
                                    className="px-4 py-2 rounded-lg font-medium text-gray-700 dark:text-slate-200 bg-gray-100 dark:bg-slate-700 hover:bg-gray-200 dark:hover:bg-slate-600 transition-all"
                                >
                                    Back
                                </button>
                                <button
                                    onClick={handleConfirm}
                                    disabled={loading}
                                    className={`px-4 py-2 rounded-lg font-medium transition-all ${
                                        loading
                                            ? 'bg-gray-300 dark:bg-slate-600 text-gray-500 dark:text-slate-400 cursor-not-allowed'
                                            : 'bg-accent-600 text-white hover:bg-accent-700 cursor-pointer'
                                    }`}
                                >
                                    {loading ? 'Adding\u2026' : 'Confirm & Add'}
                                </button>
                            </div>
                        </div>
                    )}

                    {step === 'success' && confirmData && (
                        <div className="space-y-4">
                            <div className="flex items-center gap-2">
                                <span className="text-green-600 dark:text-green-400 text-xl">&#10003;</span>
                                <p className="font-semibold text-gray-900 dark:text-white">
                                    {confirmData.project_name || `Project ${confirmData.project_id}`} added successfully
                                </p>
                            </div>

                            <div className="border-t border-gray-200 dark:border-slate-600 pt-4 space-y-3">
                                <div>
                                    <p className="text-sm font-semibold text-gray-700 dark:text-slate-200">Webhook</p>
                                    <p className="text-sm text-gray-600 dark:text-slate-300 capitalize">
                                        {confirmData.webhook_result?.status}
                                        {confirmData.webhook_result?.hook_id ? ` (ID: ${confirmData.webhook_result.hook_id})` : ''}
                                    </p>
                                </div>
                                <div>
                                    <p className="text-sm font-semibold text-gray-700 dark:text-slate-200">Submittals</p>
                                    <p className="text-sm text-gray-600 dark:text-slate-300">
                                        {confirmData.sync_result?.created ?? 0} created,{' '}
                                        {confirmData.sync_result?.skipped ?? 0} skipped,{' '}
                                        {confirmData.sync_result?.errors ?? 0} errors
                                    </p>
                                </div>
                            </div>

                            <div className="flex justify-end pt-2">
                                <button
                                    onClick={resetAndClose}
                                    className="px-4 py-2 rounded-lg font-medium bg-accent-600 text-white hover:bg-accent-700 transition-all cursor-pointer"
                                >
                                    Close
                                </button>
                            </div>
                        </div>
                    )}

                    {step === 'error' && (
                        <div className="space-y-4">
                            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                                <p className="text-sm font-semibold text-red-700 dark:text-red-400 mb-1">Error</p>
                                <p className="text-sm text-red-600 dark:text-red-300">{errorMessage}</p>
                            </div>
                            <div className="flex justify-end gap-3 pt-2">
                                <button
                                    onClick={resetAndClose}
                                    className="px-4 py-2 rounded-lg font-medium text-gray-700 dark:text-slate-200 bg-gray-100 dark:bg-slate-700 hover:bg-gray-200 dark:hover:bg-slate-600 transition-all"
                                >
                                    Close
                                </button>
                                <button
                                    onClick={() => { setStep('input'); setErrorMessage(null); }}
                                    className="px-4 py-2 rounded-lg font-medium bg-accent-600 text-white hover:bg-accent-700 transition-all cursor-pointer"
                                >
                                    Try Again
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
