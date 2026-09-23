/**
 * @milehigh-header
 * schema_version: 1
 * purpose: /m/todos — the employee's phone To-Dos: the shared TodosMobile body wired to the staff
 *          routes (/brain/todos, /brain/notifications). Tapping a release opens the normal staff
 *          ReleaseHubModal (phone-tuned in PR #376), resolved against the shared ReleasesContext.
 * exports:
 *   StaffMobileTodos: Page component under StaffMobileShell.
 * imports_from: [react, react-router-dom, ../../services/todosApi, ../../services/notificationApi,
 *                ../../components/mobile/TodosMobile, ../../components/ReleaseHubModal, ../../hooks/useDaySchedule]
 * imported_by: [App.jsx]
 */
import { useMemo } from 'react';
import { useOutletContext } from 'react-router-dom';
import TodosMobile from '../../components/mobile/TodosMobile';
import { ReleaseHubModal } from '../../components/ReleaseHubModal';
import { useReleaseHub } from '../../hooks/useDaySchedule';
import { fetchTodos, setTodoStatus } from '../../services/todosApi';
import { fetchNotifications, markNotificationRead, markAllRead, MENTION_TYPES, TODO_TYPES as STAFF_TODO_TYPES } from '../../services/notificationApi';

export default function StaffMobileTodos() {
    const { unread, refreshUnread } = useOutletContext();
    const { hubJob, openRelease, closeHub } = useReleaseHub();

    const api = useMemo(() => ({
        listTodos: () => fetchTodos({ status: 'all' }).then((d) => (d.todos || []).map((t) => ({
            id: t.id, title: t.title, detail: t.detail, item_type: t.item_type, status: t.status,
            due_date: t.due_date, release_id: t.release_id,
            release_code: t.release_job_release, release_job_name: t.matched_job_name,
        }))),
        setTodoStatus,
        listNotifications: () => fetchNotifications({ types: [...MENTION_TYPES, ...STAFF_TODO_TYPES], limit: 50 })
            .then((d) => (d.notifications || []).map((n) => ({
                ...n,
                release_code: n.release_job_number && n.release_number ? `${n.release_job_number}-${n.release_number}` : null,
            }))),
        markRead: markNotificationRead,
        markAllRead,
        todoTypes: STAFF_TODO_TYPES,
        mentionTypes: MENTION_TYPES,
    }), []);

    return (
        <>
            <TodosMobile api={api} unreadTodos={unread?.unread_todos || 0} refreshUnread={refreshUnread}
                onOpenRelease={(id) => openRelease({ release_id: id })} />
            <ReleaseHubModal isOpen={!!hubJob} job={hubJob} releaseId={hubJob?.id} viewerUrl={hubJob?.viewer_url}
                initialTab="details" onClose={closeHub} />
        </>
    );
}
