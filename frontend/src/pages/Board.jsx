/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Admin-only Kanban board for tracking bugs, features, and tasks with drag-and-drop reordering and cross-column status changes.
 * exports:
 *   Board: Page component rendering four-column Kanban (Open, In Progress, Deployed, Closed) with detail panel
 * imports_from: [react, react-router-dom, ../utils/auth, ../services/boardApi, ../components/board/BoardDetail, ../components/board/NewItemModal, @dnd-kit/core, @dnd-kit/sortable]
 * imported_by: [App.jsx]
 * invariants:
 *   - Requires admin role; non-admins see an access-denied message
 *   - Drag between columns triggers a status update API call; within-column drag triggers a reorder API call
 *   - Optimistic UI updates revert on API failure
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { checkAuth } from '../utils/auth';
import { fetchBoardItems, fetchBoardItem, updateBoardItem, reorderBoardItems } from '../services/boardApi';
import BoardDetail from '../components/board/BoardDetail';
import NewItemModal from '../components/board/NewItemModal';
import {
    DndContext,
    DragOverlay,
    PointerSensor,
    useSensor,
    useSensors,
    closestCenter,
    useDroppable,
} from '@dnd-kit/core';
import {
    SortableContext,
    useSortable,
    verticalListSortingStrategy,
    arrayMove,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

const STATUSES = [
    { value: 'open',        label: 'Open',        dot: 'bg-blue-400',    bg: 'bg-blue-50 dark:bg-blue-950/30',      border: 'border-blue-200 dark:border-blue-800/40',    gradientTop: 'rgba(254, 240, 138, 0.18)' },
    { value: 'in_progress', label: 'In Progress',  dot: 'bg-yellow-400',  bg: 'bg-yellow-50 dark:bg-yellow-950/30',  border: 'border-yellow-200 dark:border-yellow-800/40', gradientTop: 'rgba(254, 215, 170, 0.20)' },
    { value: 'deployed',    label: 'Deployed',     dot: 'bg-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-950/30', border: 'border-emerald-200 dark:border-emerald-800/40', gradientTop: 'rgba(187, 247, 208, 0.20)' },
    { value: 'closed',      label: 'Closed',       dot: 'bg-gray-400',    bg: 'bg-gray-50 dark:bg-gray-800/30',      border: 'border-gray-200 dark:border-gray-700',        gradientTop: 'rgba(203, 213, 225, 0.15)' },
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

function isNew(isoString) {
    if (!isoString) return false;
    const ts = isoString.endsWith('Z') ? isoString : isoString + 'Z';
    return (Date.now() - new Date(ts).getTime()) < 48 * 60 * 60 * 1000;
}

function KanbanCard({ item, isSelected, onClick }) {
    const hasPriorityDot = item.priority === 'urgent' || item.priority === 'high';
    const cardNew = !isSelected && isNew(item.created_at);
    return (
        <div
            onClick={onClick}
            className={`w-full text-left rounded-lg border p-2.5 transition-all cursor-grab active:cursor-grabbing
                ${isSelected
                    ? 'bg-accent-50 dark:bg-accent-900/20 border-accent-300 dark:border-accent-600 ring-1 ring-accent-400/50 shadow-md'
                    : cardNew
                        ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-700 hover:border-yellow-300 dark:hover:border-yellow-600 hover:shadow-sm'
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

function SortableKanbanCard({ item, isSelected, onClick }) {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.id });
    return (
        <div
            ref={setNodeRef}
            style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.4 : 1 }}
            {...attributes}
            {...listeners}
        >
            <KanbanCard item={item} isSelected={isSelected} onClick={onClick} />
        </div>
    );
}

function KanbanColumn({ status, items, selectedId, onCardClick, isOver }) {
    const { setNodeRef } = useDroppable({ id: status.value });
    const itemIds = items.map(i => i.id);
    return (
        <div className="flex flex-col min-w-0 flex-1">
            <div className={`flex items-center gap-2 px-2.5 py-2 rounded-t-lg border ${status.border} ${status.bg}`}>
                <span className={`w-2 h-2 rounded-full ${status.dot}`} />
                <span className="text-xs font-semibold text-gray-700 dark:text-slate-200">{status.label}</span>
                <span className="text-[10px] text-gray-400 dark:text-slate-500 font-medium">{items.length}</span>
            </div>
            <div
                ref={setNodeRef}
                style={{ background: `linear-gradient(to bottom, ${status.gradientTop} 0%, transparent 40%)` }}
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
                <SortableContext items={itemIds} strategy={verticalListSortingStrategy}>
                    {items.map(item => (
                        <SortableKanbanCard
                            key={item.id}
                            item={item}
                            isSelected={selectedId === item.id}
                            onClick={() => onCardClick(item)}
                        />
                    ))}
                </SortableContext>
            </div>
        </div>
    );
}

export default function Board() {
    const location = useLocation();
    const [isAdmin, setIsAdmin] = useState(false);
    const [loading, setLoading] = useState(true);
    const [items, setItems] = useState([]);
    const [selectedItem, setSelectedItem] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [showNewModal, setShowNewModal] = useState(false);
    const [activeItem, setActiveItem] = useState(null);
    const [overColumnId, setOverColumnId] = useState(null);

    const [categoryFilter, setCategoryFilter] = useState('All');
    const [searchText, setSearchText] = useState('');
    const [debouncedSearch, setDebouncedSearch] = useState('');

    const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

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
            position: null,
        }, ...prev]);
    };

    // Open specific item from notification navigation
    useEffect(() => {
        const openItemId = location.state?.openItemId;
        if (openItemId && isAdmin) {
            fetchBoardItem(openItemId).then(setSelectedItem).catch(() => {});
        }
    }, [location.state, isAdmin]);

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
    for (const s of STATUSES) {
        columns[s.value].sort((a, b) => {
            const pa = a.position ?? Number.MAX_SAFE_INTEGER;
            const pb = b.position ?? Number.MAX_SAFE_INTEGER;
            if (pa !== pb) return pa - pb;
            return new Date(b.updated_at) - new Date(a.updated_at);
        });
    }

    const handleDragEnd = async ({ active, over }) => {
        setActiveItem(null);
        setOverColumnId(null);
        if (!over || active.id === over.id) return;

        const activeStatus = items.find(i => i.id === active.id)?.status;
        const overIsColumn = typeof over.id === 'string';
        const overStatus = overIsColumn ? over.id : items.find(i => i.id === over.id)?.status;
        if (!activeStatus || !overStatus) return;

        if (activeStatus === overStatus) {
            // Within-column reorder
            const col = columns[activeStatus];
            const oldIndex = col.findIndex(i => i.id === active.id);
            const newIndex = col.findIndex(i => i.id === over.id);
            if (oldIndex === newIndex || newIndex === -1) return;

            const reordered = arrayMove(col, oldIndex, newIndex);
            const orderedIds = reordered.map(i => i.id);
            const posMap = Object.fromEntries(orderedIds.map((id, idx) => [id, idx]));

            // Optimistic update
            setItems(prev => prev.map(i => posMap[i.id] !== undefined ? { ...i, position: posMap[i.id] } : i));

            try {
                await reorderBoardItems(activeStatus, orderedIds);
            } catch {
                // Revert to original positions
                setItems(prev => prev.map(i => {
                    const orig = col.find(c => c.id === i.id);
                    return orig ? { ...i, position: orig.position } : i;
                }));
            }
        } else {
            // Between-column status change
            const draggedItem = items.find(i => i.id === active.id);
            if (!draggedItem) return;

            setItems(prev => prev.map(i => i.id === active.id ? { ...i, status: overStatus } : i));
            if (selectedItem?.id === active.id) {
                setSelectedItem(prev => prev ? { ...prev, status: overStatus } : prev);
            }

            try {
                const updated = await updateBoardItem(active.id, { status: overStatus });
                setItems(prev => prev.map(i => i.id === active.id
                    ? { ...i, status: updated.status, updated_at: updated.updated_at }
                    : i
                ));
                if (selectedItem?.id === active.id) setSelectedItem(updated);
            } catch {
                setItems(prev => prev.map(i => i.id === active.id ? { ...i, status: draggedItem.status } : i));
            }
        }
    };

    return (
        <div className="flex flex-col h-[calc(100vh-3.5rem)] overflow-hidden">
            {/* Header bar */}
            <div className="shrink-0 px-5 py-2.5 flex items-center gap-3 border-b border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900">
                <h1 className="text-lg font-bold text-accent-600 dark:text-accent-300 tracking-tight">Bug Tracker</h1>

                <div className="flex items-center gap-1 ml-3">
                    {CATEGORY_FILTERS.map(c => (
                        <button key={c} onClick={() => setCategoryFilter(c)}
                            className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                                categoryFilter === c
                                    ? 'bg-accent-500 text-white dark:bg-accent-400 dark:text-slate-900'
                                    : 'text-gray-500 dark:text-slate-400 hover:bg-accent-50 dark:hover:bg-slate-700'
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
                <DndContext
                    sensors={sensors}
                    collisionDetection={closestCenter}
                    onDragStart={({ active }) => setActiveItem(items.find(i => i.id === active.id) ?? null)}
                    onDragOver={({ over }) => setOverColumnId(typeof over?.id === 'string' ? over.id : null)}
                    onDragEnd={handleDragEnd}
                >
                    {/* Kanban columns */}
                    <div className={`flex gap-2.5 p-3 min-h-0 overflow-x-auto transition-all ${selectedItem ? 'w-[60%]' : 'w-full'}`}>
                        {STATUSES.map(status => (
                            <KanbanColumn
                                key={status.value}
                                status={status}
                                items={columns[status.value]}
                                selectedId={selectedItem?.id}
                                onCardClick={handleCardClick}
                                isOver={overColumnId === status.value}
                            />
                        ))}
                    </div>

                    <DragOverlay>
                        {activeItem && (
                            <div className="rotate-1 shadow-xl opacity-95 w-52">
                                <KanbanCard item={activeItem} isSelected={false} onClick={() => {}} />
                            </div>
                        )}
                    </DragOverlay>
                </DndContext>

                {/* Right detail panel */}
                {selectedItem && (
                    <div className="w-[40%] border-l border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4 overflow-hidden">
                        <BoardDetail key={selectedItem.id} item={selectedItem} onUpdate={handleItemUpdate} onClose={() => setSelectedItem(null)} />
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
