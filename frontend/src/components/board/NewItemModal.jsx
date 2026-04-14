/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Renders a portal-based modal form for creating new board items with title, body, category, and priority fields.
 * exports:
 *   NewItemModal: Modal dialog that collects board item details and calls createBoardItem on submit
 * imports_from: [react, react-dom, ../../services/boardApi]
 * imported_by: [pages/Board.jsx]
 * invariants:
 *   - Renders via createPortal to document.body so it overlays all other content
 *   - Category options are hardcoded to match backend-accepted values
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { useState } from 'react';
import { createPortal } from 'react-dom';
import { createBoardItem } from '../../services/boardApi';

const CATEGORIES = ['Drafting WL', 'Job Log', 'General'];
const PRIORITIES = [
    { value: 'low', label: 'Low' },
    { value: 'normal', label: 'Normal' },
    { value: 'high', label: 'High' },
    { value: 'urgent', label: 'Urgent' },
];

export default function NewItemModal({ onClose, onCreated }) {
    const [title, setTitle] = useState('');
    const [body, setBody] = useState('');
    const [category, setCategory] = useState(CATEGORIES[0]);
    const [priority, setPriority] = useState('normal');
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!title.trim()) {
            setError('Title is required');
            return;
        }
        setSubmitting(true);
        setError('');
        try {
            const item = await createBoardItem({ title: title.trim(), body: body.trim(), category, priority });
            onCreated(item);
        } catch (err) {
            setError(err.response?.data?.error || 'Failed to create item');
        } finally {
            setSubmitting(false);
        }
    };

    return createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" onClick={onClose}>
            <div
                className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-w-lg w-full mx-4"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="bg-gradient-to-r from-accent-500 to-accent-600 px-6 py-4 rounded-t-xl">
                    <div className="flex items-center justify-between">
                        <h2 className="text-xl font-bold text-white">New Item</h2>
                        <button onClick={onClose} className="text-white hover:text-gray-200 text-2xl leading-none">&times;</button>
                    </div>
                </div>

                <form onSubmit={handleSubmit} className="p-6 space-y-4">
                    {error && (
                        <div className="bg-red-50 dark:bg-red-900/30 border-l-4 border-red-500 p-3 text-sm text-red-700 dark:text-red-200">
                            {error}
                        </div>
                    )}

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Title</label>
                        <input
                            type="text"
                            value={title}
                            onChange={(e) => setTitle(e.target.value)}
                            className="w-full px-4 py-2.5 border border-gray-300 dark:border-slate-500 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white dark:bg-slate-600 dark:text-slate-100"
                            placeholder="Short summary of the issue or feature"
                            autoFocus
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Details (optional)</label>
                        <textarea
                            value={body}
                            onChange={(e) => setBody(e.target.value)}
                            rows={3}
                            className="w-full px-4 py-2.5 border border-gray-300 dark:border-slate-500 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent bg-white dark:bg-slate-600 dark:text-slate-100 resize-y"
                            placeholder="Additional context, steps to reproduce, etc."
                        />
                    </div>

                    <div className="flex gap-4">
                        <div className="flex-1">
                            <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Category</label>
                            <select
                                value={category}
                                onChange={(e) => setCategory(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 dark:border-slate-500 rounded-lg text-sm bg-white dark:bg-slate-600 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-500"
                            >
                                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                        </div>
                        <div className="flex-1">
                            <label className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1">Priority</label>
                            <select
                                value={priority}
                                onChange={(e) => setPriority(e.target.value)}
                                className="w-full px-3 py-2 border border-gray-300 dark:border-slate-500 rounded-lg text-sm bg-white dark:bg-slate-600 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-accent-500"
                            >
                                {PRIORITIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                            </select>
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="flex justify-end gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-slate-200 bg-gray-200 dark:bg-slate-600 hover:bg-gray-300 dark:hover:bg-slate-500 rounded-lg transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={submitting}
                            className="px-4 py-2 text-sm font-medium text-white bg-accent-500 hover:bg-accent-600 rounded-lg disabled:opacity-50 transition-colors"
                        >
                            {submitting ? 'Creating...' : 'Create'}
                        </button>
                    </div>
                </form>
            </div>
        </div>,
        document.body
    );
}
