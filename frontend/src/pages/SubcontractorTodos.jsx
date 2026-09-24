/**
 * @milehigh-header
 * schema_version: 2
 * purpose: The subcontractor's To-Dos tab — the shared phone To-Dos body (components/mobile/
 *          TodosMobile) wired to the sub-scoped routes. Tapping a release pushes /sub/releases/:id.
 * exports:
 *   SubcontractorTodos: Page component, rendered inside SubcontractorShell's Outlet.
 * imports_from: [react, react-router-dom, ../services/subPortalApi, ../components/mobile/TodosMobile]
 * imported_by: [App.jsx]
 * invariants:
 *   - Everything shown is server-scoped to this account; the adapter passes no owner.
 */
import { useMemo } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import TodosMobile from '../components/mobile/TodosMobile';
import {
    listSubTodos, setSubTodoStatus, listSubNotifications, markSubNotificationRead, markAllSubRead,
    TODO_NOTIFICATION_TYPES, MENTION_NOTIFICATION_TYPES,
} from '../services/subPortalApi';

export default function SubcontractorTodos() {
    const { refreshUnread, unread } = useOutletContext();
    const navigate = useNavigate();
    const api = useMemo(() => ({
        listTodos: () => listSubTodos('all'),
        setTodoStatus: setSubTodoStatus,
        listNotifications: () => listSubNotifications(50).then((d) => d.notifications),
        markRead: markSubNotificationRead,
        markAllRead: markAllSubRead,
        todoTypes: TODO_NOTIFICATION_TYPES,
        mentionTypes: MENTION_NOTIFICATION_TYPES,
    }), []);
    return (
        <TodosMobile api={api} unreadTodos={unread?.unread_todos || 0} refreshUnread={refreshUnread}
            onOpenRelease={(id) => navigate(`/sub/releases/${id}`)} />
    );
}
