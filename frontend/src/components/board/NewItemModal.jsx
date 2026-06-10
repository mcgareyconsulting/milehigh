/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Renders a portal-based modal form for creating new board items with title, body, category, priority, and optional photo attachments.
 * exports:
 *   NewItemModal: Modal dialog that collects board item details (and staged photos) and calls createBoardItem + uploadBoardPhoto on submit
 * imports_from: [react, react-dom, ../../services/boardApi]
 * imported_by: [pages/Board.jsx]
 * invariants:
 *   - Renders via createPortal to document.body so it overlays all other content
 *   - Category options are hardcoded to match backend-accepted values
 *   - Photos are staged client-side until submit; the card is created first, then each staged image is uploaded to its id
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { createBoardItem, uploadBoardPhoto } from '../../services/boardApi';

const CATEGORIES = ['Drafting WL', 'Job Log', 'General'];
const PRIORITIES = [
    { value: 'low', label: 'Low' },
    { value: 'normal', label: 'Normal' },
    { value: 'high', label: 'High' },
    { value: 'urgent', label: 'Urgent' },
];

const isImageFile = (file) =>
    (file?.type || '').toLowerCase().startsWith('image/') ||
    /\.(png|jpe?g|gif|webp|bmp|heic|heif|tiff?)$/i.test(file?.name || '');

export default function NewItemModal({ onClose, onCreated }) {
    const [title, setTitle] = useState('');
    const [body, setBody] = useState('');
    const [category, setCategory] = useState(CATEGORIES[0]);
    const [priority, setPriority] = useState('normal');
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState('');
    // Photos staged client-side (each: {id, file, url}); uploaded after the card is created.
    const [staged, setStaged] = useState([]);
    const [dragOver, setDragOver] = useState(false);

    const fileInputRef = useRef(null);
    const cameraInputRef = useRef(null);
    const idCounter = useRef(0);

    const addFiles = useCallback((files) => {
        const images = Array.from(files || []).filter(isImageFile);
        if (images.length === 0) return;
        setStaged((prev) => [
            ...prev,
            ...images.map((file) => ({ id: idCounter.current++, file, url: URL.createObjectURL(file) })),
        ]);
    }, []);

    const removeStaged = (id) => {
        setStaged((prev) => {
            const target = prev.find((s) => s.id === id);
            if (target) URL.revokeObjectURL(target.url);
            return prev.filter((s) => s.id !== id);
        });
    };

    // Revoke any outstanding object URLs on unmount.
    useEffect(() => () => {
        setStaged((prev) => { prev.forEach((s) => URL.revokeObjectURL(s.url)); return prev; });
    }, []);

    // Capture clipboard pastes while the modal is open (key affordance for screenshots).
    useEffect(() => {
        const onPaste = (e) => {
            const items = e.clipboardData?.items;
            if (!items) return;
            const files = [];
            for (const it of items) {
                if (it.kind === 'file') {
                    const f = it.getAsFile();
                    if (f && isImageFile(f)) files.push(f);
                }
            }
            if (files.length) {
                e.preventDefault();
                addFiles(files);
            }
        };
        document.addEventListener('paste', onPaste);
        return () => document.removeEventListener('paste', onPaste);
    }, [addFiles]);

    const handleFilePick = (e) => {
        if (e.target.files?.length) addFiles(e.target.files);
        e.target.value = '';
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setDragOver(false);
        if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
    };

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
            // Card exists now — upload staged photos to it sequentially. Tolerate
            // individual photo failures so a flaky upload never loses the card; any
            // that fail simply won't appear in the card's photo grid, which opens next.
            for (const s of staged) {
                try {
                    await uploadBoardPhoto(item.id, s.file);
                } catch {
                    console.error('Failed to upload staged photo for new board item', item.id);
                }
            }
            staged.forEach((s) => URL.revokeObjectURL(s.url));
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
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
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

                    <div>
                        <div className="flex items-center gap-2 mb-1">
                            <label className="block text-sm font-medium text-gray-700 dark:text-slate-300">Photos (optional)</label>
                            <button
                                type="button"
                                onClick={() => fileInputRef.current?.click()}
                                className="px-2 py-0.5 text-xs font-medium text-gray-600 dark:text-slate-300 bg-gray-100 dark:bg-slate-700 hover:bg-gray-200 dark:hover:bg-slate-600 rounded"
                            >
                                Add
                            </button>
                            <button
                                type="button"
                                onClick={() => cameraInputRef.current?.click()}
                                className="px-2 py-0.5 text-xs font-medium text-gray-600 dark:text-slate-300 bg-gray-100 dark:bg-slate-700 hover:bg-gray-200 dark:hover:bg-slate-600 rounded sm:hidden"
                            >
                                Camera
                            </button>
                        </div>
                        <input ref={fileInputRef} type="file" accept="image/*" multiple onChange={handleFilePick} className="hidden" />
                        <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" onChange={handleFilePick} className="hidden" />
                        <div className={`rounded-lg border border-dashed px-3 py-2.5 transition-colors ${
                            dragOver ? 'border-accent-500 bg-accent-50 dark:bg-accent-900/20' : 'border-gray-300 dark:border-slate-500'
                        }`}>
                            {staged.length === 0 ? (
                                <p className="text-xs text-gray-400 dark:text-slate-500">
                                    Paste a screenshot, drop images here, or use Add.
                                </p>
                            ) : (
                                <div className="grid grid-cols-4 gap-2">
                                    {staged.map((s) => (
                                        <div key={s.id} className="group relative">
                                            <img src={s.url} alt={s.file.name} className="w-full h-16 object-cover rounded-md border border-gray-200 dark:border-slate-600" />
                                            <button
                                                type="button"
                                                onClick={() => removeStaged(s.id)}
                                                className="absolute top-0.5 right-0.5 w-5 h-5 flex items-center justify-center rounded-full bg-black/50 text-white text-xs opacity-0 group-hover:opacity-100 transition-opacity hover:bg-red-600"
                                                title="Remove"
                                            >
                                                &times;
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
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
                            {submitting ? (staged.length ? 'Creating & uploading…' : 'Creating...') : 'Create'}
                        </button>
                    </div>
                </form>
            </div>
        </div>,
        document.body
    );
}
