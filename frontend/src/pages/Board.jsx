import { useState, useEffect, useCallback, useRef } from 'react';
import { checkAuth } from '../utils/auth';
import { fetchBoardItems, fetchBoardItem, updateBoardItem } from '../services/boardApi';
import BoardDetail from '../components/board/BoardDetail';
import NewItemModal from '../components/board/NewItemModal';

const STATUSES = [
    { value: 'open', label: 'Open', dot: 'bg-blue-400', bg: 'bg-blue-50 dark:bg-blue-950/30', border: 'border-blue-200 dark:border-blue-800/40' },
    { value: 'in_progress', label: 'In Progress', dot: 'bg-yellow-400', bg: 'bg-yellow-50 dark:bg-yellow-950/30', border: 'border-yellow-200 dark:border-yellow-800/40' },
    { value: 'deployed', label: 'Deployed', dot: 'bg-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-950/30', border: 'border-emerald-200 dark:border-emerald-800/40' },
    { value: 'closed', label: 'Closed', dot: 'bg-gray-400', bg: 'bg-gray-50 dark:bg-gray-800/30', border: 'border-gray-200 dark:border-gray-700' },
];

const CATEGORY_COLORS = {
    'Job Log': 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300',
    'Drafting WL': 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300',
    'General': 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
};

const PRIORITY_DOT = {
    urgent: 'bg-red-500',
    high: 'bg-orange-400',
    normal: 'bg-transparent',
    low: 'bg-transparent',
};

const CATEGORY_FILTERS = ['All', 'Drafting WL', 'Job Log', 'General'];

function timeAgo(isoString) {
    if (!isoString) return '';
    const ts = isoString.endsWith('Z') ? isoString : isoString + 'Z';
    const diff = Date.now() - new Date(ts).getTime();
    if (diff < 0) return 'now';
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'now';
    if (mins < 60) return `${mins}m`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h`;
    return `${Math.floor(hrs / 24)}d`;
}

function KanbanCard({ item, isSelected, onClick, onDragStart }) {
    const hasPriorityDot = item.priority === 'urgent' || item.priority === 'high';
    return (
        <div
            draggable
            onDragStart={(e) => {
                e.dataTransfer.setData('text/plain', String(item.id));
                e.dataTransfer.effectAllowed = 'move';
                onDragStart(item.id);
            }}
            onClick={onClick}
            className={`w-full text-left rounded-lg border p-2.5 transition-all cursor-grab active:cursor-grabbing
                ${isSelected
                    ? 'bg-accent-50 dark:bg-accent-900/20 border-accent-300 dark:border-accent-600 ring-1 ring-accent-400/50 shadow-md'
                    : 'bg-white dark:bg-slate-800 border-gray-200 dark:border-slate-700 hover:border-gray-300 dark:hover:border-slate-600 hover:shadow-sm'
                }`}
        >
            <div className="flex items-start gap-1.5">
                {hasPriorityDot && (
                    <span className={`mt-1.5 shrink-0 w-2 h-2 rounded-full ${PRIORITY_DOT[item.priority]}`} />
                )}
                <h3 className="text-xs font-medium text-gray-900 dark:text-slate-100 leading-snug line-clamp-2">
                    {item.title}
                </h3>
            </div>
            <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
                <span className={`px-1.5 py-0.5 text-[10px] font-medium rounded ${CATEGORY_COLORS[item.category] || CATEGORY_COLORS['General']}`}>
                    {item.category}
                </span>
                <span className="ml-auto flex items-center gap-1 text-[10px] text-gray-400 dark:text-slate-500">
                    {item.activity_count > 0 && (
                        <span className="flex items-center gap-0.5">
                            <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                            </svg>
                            {item.activity_count}
                        </span>
                    )}
                    <span>{timeAgo(item.updated_at)}</span>
                </span>
            </div>
        </div>
    );
}

function KanbanColumn({ status, items, selectedId, onCardClick, onDragStart, onDrop, dragOverStatus }) {
    const isOver = dragOverStatus === status.value;
    return (
        <div className="flex flex-col min-w-0 flex-1">
            <div className={`flex items-center gap-2 px-2.5 py-2 rounded-t-lg border ${status.border} ${status.bg}`}>
                <span className={`w-2 h-2 rounded-full ${status.dot}`} />
                <span className="text-xs font-semibold text-gray-700 dark:text-slate-200">{status.label}</span>
                <span className="text-[10px] text-gray-400 dark:text-slate-500 font-medium">{items.length}</span>
            </div>
            <div
                onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }}
                onDragEnter={(e) => { e.preventDefault(); onDrop('hover', status.value); }}
                onDragLeave={(e) => {
                    if (!e.currentTarget.contains(e.relatedTarget)) onDrop('leave', status.value);
                }}
                onDrop={(e) => {
                    e.preventDefault();
                    const itemId = parseInt(e.dataTransfer.getData('text/plain'), 10);
                    if (itemId) onDrop('drop', status.value, itemId);
                }}
                className={`flex-1 overflow-y-auto p-1.5 space-y-1.5 border-x border-b rounded-b-lg transition-colors ${status.border}
                    ${isOver
                        ? 'bg-accent-50/50 dark:bg-accent-900/10 ring-2 ring-inset ring-accent-300 dark:ring-accent-600'
                        : 'bg-gray-50/50 dark:bg-slate-900/30'
                    }`}
            >
                {items.length === 0 && (
                    <div className={`py-6 text-center text-[10px] ${isOver ? 'text-accent-500' : 'text-gray-400 dark:text-slate-600'}`}>
                        {isOver ? 'Drop here' : 'No items'}
                    </div>
                )}
                {items.map(item => (
                    <KanbanCard key={item.id} item={item} isSelected={selectedId === item.id} onClick={() => onCardClick(item)} onDragStart={onDragStart} />
                ))}
            </div>
        </div>
    );
}

export default function Board() {
    const [isAdmin, setIsAdmin] = useState(false);
    const [loading, setLoading] = useState(true);
    const [items, setItems] = useState([]);
    const [selectedItem, setSelectedItem] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [showNewModal, setShowNewModal] = useState(false);
    const [draggingId, setDraggingId] = useState(null);
    const [dragOverStatus, setDragOverStatus] = useState(null);

    const [categoryFilter, setCategoryFilter] = useState('All');
    const [searchText, setSearchText] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');

    const debounceRef = useRef(null);
    useEffect(() => {
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => setDebouncedSearch(searchText), 300);
        return () => clearTimeout(debounceRef.current);
    }, [searchText]);

    const loadItems = useCallback(async () => {
        const filters = {};
        if (categoryFilter !== 'All') filters.category = categoryFilter;
        if (debouncedSearch.trim()) filters.search = debouncedSearch.trim();
        const data = await fetchBoardItems(filters);
        setItems(data);
    }, [categoryFilter, debouncedSearch]);

    useEffect(() => { checkAuth().then(u => { setIsAdmin(u?.is_admin || false); setLoading(false); }); }, []);
    useEffect(() => { if (isAdmin) loadItems(); }, [isAdmin, loadItems]);

    const handleCardClick = async (item) => {
        if (selectedItem?.id === item.id) { setSelectedItem(null); return; }
        setDetailLoading(true);
        try { const full = await fetchBoardItem(item.id); setSelectedItem(full); }
        finally { setDetailLoading(false); }
    };

    const handleDragStart = (itemId) => {
        setDraggingId(itemId);
    };

    const handleColumnDrop = async (action, statusValue, itemId) => {
        if (action === 'hover') {
            setDragOverStatus(statusValue);
            return;
        }
        if (action === 'leave') {
            setDragOverStatus(null);
            return;
        }
        // action === 'drop'
        setDragOverStatus(null);
        setDraggingId(null);

        const draggedItem = items.find(i => i.id === itemId);
        if (!draggedItem || draggedItem.status === statusValue) return;

        // Optimistic update
        setItems(prev => prev.map(i => i.id === itemId ? { ...i, status: statusValue } : i));
        if (selectedItem?.id === itemId) {
            setSelectedItem(prev => prev ? { ...prev, status: statusValue } : prev);
        }

        // Persist to backend
        try {
            const updated = await updateBoardItem(itemId, { status: statusValue });
            // Sync with server response
            setItems(prev => prev.map(i => i.id === itemId ? {
                ...i, status: updated.status, updated_at: updated.updated_at,
            } : i));
            if (selectedItem?.id === itemId) {
                setSelectedItem(updated);
            }
        } catch {
            // Revert on failure
            setItems(prev => prev.map(i => i.id === itemId ? { ...i, status: draggedItem.status } : i));
        }
    };

    // Clear drag state when drag ends anywhere
    useEffect(() => {
        const onDragEnd = () => { setDraggingId(null); setDragOverStatus(null); };
        window.addEventListener('dragend', onDragEnd);
        return () => window.removeEventListener('dragend', onDragEnd);
    }, []);

    const handleItemUpdate = (updated) => {
        if (updated === null) {
            setItems(prev => prev.filter(i => i.id !== selectedItem?.id));
            setSelectedItem(null);
            return;
        }
        setSelectedItem(updated);
        setItems(prev => prev.map(i => i.id === updated.id ? {
            ...i, title: updated.title, status: updated.status, priority: updated.priority,
            category: updated.category, updated_at: updated.updated_at,
            activity_count: updated.activity?.filter(a => a.type === 'comment').length ?? i.activity_count,
        } : i));
    };

    const handleItemCreated = (item) => {
        setShowNewModal(false);
        setSelectedItem(item);
        setItems(prev => [{
            id: item.id, title: item.title, body: item.body, category: item.category,
            status: item.status, priority: item.priority, author_id: item.author_id,
            author_name: item.author_name, created_at: item.created_at,
            updated_at: item.updated_at, activity_count: 0,
        }, ...prev]);
    };

    useEffect(() => {
        const onKey = (e) => { if (e.key === 'Escape') setSelectedItem(null); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, []);

    if (loading) return <div className="flex-1 flex items-center justify-center"><span className="text-gray-500 dark:text-slate-400">Loading...</span></div>;
    if (!isAdmin) return <div className="flex-1 flex items-center justify-center"><span className="text-gray-500 dark:text-slate-400">Admin access required.</span></div>;

    const columns = {};
    for (const s of STATUSES) columns[s.value] = [];
    for (const item of items) {
        if (columns[item.status]) columns[item.status].push(item);
        else columns.open.push(item);
    }

    return (
        <div className="flex flex-col h-[calc(100vh-3.5rem)] overflow-hidden">
            {/* Header bar */}
            <div className="shrink-0 px-5 py-2.5 flex items-center gap-3 border-b border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900">
                <h1 className="text-lg font-bold text-gray-900 dark:text-slate-100 tracking-tight">Bug Tracker</h1>

                <div className="flex items-center gap-1 ml-3">
                    {CATEGORY_FILTERS.map(c => (
                        <button key={c} onClick={() => setCategoryFilter(c)}
                            className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                                categoryFilter === c
                                    ? 'bg-gray-900 dark:bg-slate-100 text-white dark:text-slate-900'
                                    : 'text-gray-500 dark:text-slate-400 hover:bg-gray-100 dark:hover:bg-slate-800'
                            }`}>{c}</button>
                    ))}
                </div>

                <div className="relative ml-2">
                    <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 dark:text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <input type="text" value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="Search..."
                        className="pl-8 pr-3 py-1.5 text-xs border border-gray-200 dark:border-slate-600 rounded-lg bg-gray-50 dark:bg-slate-800 text-gray-700 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent w-44 placeholder:text-gray-400 dark:placeholder:text-slate-500" />
                </div>

                <button onClick={() => setShowNewModal(true)}
                    className="ml-auto px-3 py-1.5 text-xs font-semibold text-white bg-accent-500 hover:bg-accent-600 rounded-lg shadow-sm transition-colors flex items-center gap-1">
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 4v16m8-8H4" />
                    </svg>
                    New
                </button>
            </div>

            {/* Main: kanban + detail side by side */}
            <div className="flex-1 flex min-h-0 overflow-hidden">
                {/* Kanban columns */}
                <div className={`flex gap-2.5 p-3 min-h-0 overflow-x-auto transition-all ${selectedItem ? 'w-[60%]' : 'w-full'}`}>
                    {STATUSES.map(status => (
                        <KanbanColumn
                            key={status.value}
                            status={status}
                            items={columns[status.value]}
                            selectedId={selectedItem?.id}
                            onCardClick={handleCardClick}
                            onDragStart={handleDragStart}
                            onDrop={handleColumnDrop}
                            dragOverStatus={dragOverStatus}
                        />
                    ))}
                </div>

                {/* Right detail panel */}
                {selectedItem && (
                    <div className="w-[40%] border-l border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 overflow-hidden">
                        <BoardDetail item={selectedItem} onUpdate={handleItemUpdate} onClose={() => setSelectedItem(null)} />
                    </div>
                )}

                {/* Loading skeleton */}
                {detailLoading && !selectedItem && (
                    <div className="w-[40%] border-l border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
                        <div className="animate-pulse space-y-3">
                            <div className="h-4 bg-gray-200 dark:bg-slate-700 rounded w-3/4"></div>
                            <div className="h-3 bg-gray-200 dark:bg-slate-700 rounded w-1/2"></div>
                            <div className="h-20 bg-gray-200 dark:bg-slate-700 rounded"></div>
                        </div>
                    </div>
                )}
            </div>

            {showNewModal && <NewItemModal onClose={() => setShowNewModal(false)} onCreated={handleItemCreated} />}
        </div>
    );
}
