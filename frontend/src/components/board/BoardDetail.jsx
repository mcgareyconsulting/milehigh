/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Provides the detail/edit panel for a single board item, including status/priority controls, activity thread, commenting with @mentions, and deletion.
 * exports:
 *   BoardDetail: Board item detail view with inline status changes, comment thread, and delete confirmation
 * imports_from: [react, ../../services/boardApi, ../shared/MentionInput]
 * imported_by: [pages/Board.jsx]
 * invariants:
 *   - onUpdate(null) signals the item was deleted; parent must handle removal
 *   - After posting a comment, the full item is re-fetched to get server-rendered activity
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { useState, useEffect } from 'react';
import { updateBoardItem, addComment, deleteBoardItem, fetchBoardItem, fetchMentionableUsers } from '../../services/boardApi';
import MentionInput from '../shared/MentionInput';

const STATUS_OPTIONS = ['open', 'in_progress', 'deployed', 'closed'];
const PRIORITY_OPTIONS = ['low', 'normal', 'high', 'urgent'];

const STATUS_BADGE = {
    open: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
    in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
    deployed: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300',
    closed: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

const STATUS_LABELS = {
    open: 'Open',
    in_progress: 'In Progress',
    deployed: 'Deployed',
    closed: 'Closed',
};

const PRIORITY_LABELS = {
    low: 'Low',
    normal: 'Normal',
    high: 'High',
    urgent: 'Urgent',
};

function formatDate(isoString) {
    if (!isoString) return '';
    const ts = isoString.endsWith('Z') ? isoString : isoString + 'Z';
    const d = new Date(ts);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function renderCommentBody(body) {
    const parts = body.split(/(@\w+)/g);
    return parts.map((part, i) =>
        part.startsWith('@')
            ? <span key={i} className="font-semibold text-accent-500">{part}</span>
            : part
    );
}

export default function BoardDetail({ item, onUpdate, onClose }) {
    const [commentText, setCommentText] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(false);
    const [mentionableUsers, setMentionableUsers] = useState([]);

    useEffect(() => {
        fetchMentionableUsers().then(setMentionableUsers).catch(() => {});
    }, []);

    const handleStatusChange = async (newStatus) => {
        const updated = await updateBoardItem(item.id, { status: newStatus });
        onUpdate(updated);
    };

    const handlePriorityChange = async (newPriority) => {
        const updated = await updateBoardItem(item.id, { priority: newPriority });
        onUpdate(updated);
    };

    const handleComment = async (e) => {
        if (e?.preventDefault) e.preventDefault();
        if (!commentText.trim() || submitting) return;
        setSubmitting(true);
        try {
            await addComment(item.id, commentText.trim());
            setCommentText('');
            const updated = await fetchBoardItem(item.id);
            onUpdate(updated);
        } finally {
            setSubmitting(false);
        }
    };

    const handleDelete = async () => {
        await deleteBoardItem(item.id);
        onUpdate(null);
    };

    return (
        <div className="flex flex-col h-full overflow-hidden">
            {/* Header: title + close */}
            <div className="shrink-0 flex items-start gap-2 pb-3 border-b border-gray-200 dark:border-slate-700">
                <h2 className="text-sm font-bold text-gray-900 dark:text-slate-100 leading-tight flex-1">{item.title}</h2>
                <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-slate-200 text-lg leading-none shrink-0 -mt-0.5">&times;</button>
            </div>

            {/* Controls */}
            <div className="shrink-0 flex flex-wrap items-center gap-2 py-2.5 border-b border-gray-100 dark:border-slate-700/50">
                <div className="flex items-center gap-1">
                    <span className="text-[11px] text-gray-500 dark:text-slate-400">Status:</span>
                    <select value={item.status} onChange={(e) => handleStatusChange(e.target.value)}
                        className="text-[11px] px-1.5 py-0.5 rounded border border-gray-300 dark:border-slate-500 bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-accent-500">
                        {STATUS_OPTIONS.map(s => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
                    </select>
                </div>
                <div className="flex items-center gap-1">
                    <span className="text-[11px] text-gray-500 dark:text-slate-400">Priority:</span>
                    <select value={item.priority} onChange={(e) => handlePriorityChange(e.target.value)}
                        className="text-[11px] px-1.5 py-0.5 rounded border border-gray-300 dark:border-slate-500 bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-accent-500">
                        {PRIORITY_OPTIONS.map(p => <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>)}
                    </select>
                </div>
                <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-slate-300">{item.category}</span>
            </div>

            {/* Meta */}
            <div className="shrink-0 py-2 text-[11px] text-gray-400 dark:text-slate-500">
                by {item.author_name} &middot; {formatDate(item.created_at)}
            </div>

            {/* Body */}
            {item.body && (
                <div className="shrink-0 text-xs text-gray-700 dark:text-slate-300 whitespace-pre-wrap bg-gray-50 dark:bg-slate-750 rounded p-2.5 mb-2 border border-gray-100 dark:border-slate-600">
                    {item.body}
                </div>
            )}

            {/* Activity thread — scrollable, takes remaining space */}
            <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
                <h4 className="shrink-0 text-[11px] font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider mb-2">Activity</h4>
                <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
                    {(!item.activity || item.activity.length === 0) && (
                        <div className="text-xs text-gray-400 dark:text-slate-500 py-2">No activity yet.</div>
                    )}
                    {item.activity?.map((a) => (
                        <div key={a.id} className={`text-xs rounded-lg px-2.5 py-1.5 ${
                            a.type === 'status_change'
                                ? 'bg-gray-50 dark:bg-slate-750 text-gray-500 dark:text-slate-400 italic border-l-2 border-gray-300 dark:border-slate-600'
                                : 'bg-white dark:bg-slate-700 border border-gray-100 dark:border-slate-600'
                        }`}>
                            <div className="flex items-center gap-1.5 mb-0.5">
                                <span className="font-semibold text-gray-700 dark:text-slate-300">{a.author_name}</span>
                                <span className="text-gray-400 dark:text-slate-500">{formatDate(a.created_at)}</span>
                                {a.type === 'status_change' && (
                                    <span className="ml-auto flex items-center gap-1">
                                        <span className={`px-1 py-0.5 text-[10px] rounded-full ${STATUS_BADGE[a.old_value] || ''}`}>{STATUS_LABELS[a.old_value] || a.old_value}</span>
                                        <span className="text-gray-400">&rarr;</span>
                                        <span className={`px-1 py-0.5 text-[10px] rounded-full ${STATUS_BADGE[a.new_value] || ''}`}>{STATUS_LABELS[a.new_value] || a.new_value}</span>
                                    </span>
                                )}
                            </div>
                            {a.type === 'comment' && (
                                <p className="text-gray-700 dark:text-slate-300 whitespace-pre-wrap">{renderCommentBody(a.body)}</p>
                            )}
                        </div>
                    ))}
                </div>
            </div>

            {/* Comment input — pinned to bottom */}
            <form onSubmit={handleComment} className="shrink-0 flex gap-2 pt-2 border-t border-gray-100 dark:border-slate-700">
                <MentionInput
                    value={commentText}
                    onChange={setCommentText}
                    onSubmit={handleComment}
                    users={mentionableUsers}
                    placeholder="Add a comment... (type @ to mention)"
                    disabled={submitting}
                    multiline
                    rows={2}
                />
                <button type="submit" disabled={!commentText.trim() || submitting}
                    className="px-3 py-1.5 text-xs font-medium text-white bg-accent-500 hover:bg-accent-600 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                    Reply
                </button>
            </form>

            {/* Delete */}
            <div className="shrink-0 pt-2 mt-1">
                {confirmDelete ? (
                    <div className="flex items-center gap-2">
                        <span className="text-xs text-red-600 dark:text-red-400">Delete?</span>
                        <button onClick={handleDelete} className="px-2 py-0.5 text-[11px] font-medium text-white bg-red-500 hover:bg-red-600 rounded">Yes</button>
                        <button onClick={() => setConfirmDelete(false)} className="px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:text-slate-300 bg-gray-200 dark:bg-slate-600 hover:bg-gray-300 rounded">No</button>
                    </div>
                ) : (
                    <button onClick={() => setConfirmDelete(true)} className="text-[11px] text-red-500 dark:text-red-400 hover:text-red-700">Delete item</button>
                )}
            </div>
        </div>
    );
}
