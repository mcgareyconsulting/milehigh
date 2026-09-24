import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import TodosMobile from './TodosMobile';

const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Denver' }).format(new Date());

function makeApi(over = {}) {
    return {
        listTodos: vi.fn().mockResolvedValue([
            { id: 1, title: 'Bring the lift', status: 'accepted', due_date: today, release_id: 9, release_code: '560-923' },
            { id: 2, title: 'Old one', status: 'accepted', due_date: '2020-01-01' },
            { id: 3, title: 'Finished', status: 'done', due_date: null },
        ]),
        setTodoStatus: vi.fn().mockResolvedValue({}),
        listNotifications: vi.fn().mockResolvedValue([
            { id: 11, type: 'mention', message: 'Bill mentioned you', is_read: false, created_at: new Date().toISOString(), release_id: 9, release_code: '560-923' },
            { id: 12, type: 'checklist_assigned', message: 'New to-do', is_read: false, created_at: new Date().toISOString() },
        ]),
        markRead: vi.fn().mockResolvedValue({}),
        markAllRead: vi.fn().mockResolvedValue({}),
        todoTypes: ['checklist_assigned', 'checklist_due'],
        mentionTypes: ['mention'],
        ...over,
    };
}

const renderIt = (props = {}, route = '/sub/todos') => render(
    <MemoryRouter initialEntries={[route]}>
        <TodosMobile api={makeApi()} refreshUnread={vi.fn()} onOpenRelease={vi.fn()} {...props} />
    </MemoryRouter>,
);

describe('TodosMobile', () => {
    it('buckets to-dos by due date and hides done ones until asked', async () => {
        renderIt();
        await screen.findByText('Bring the lift');
        expect(screen.getByText(/Due today · 1/)).toBeInTheDocument();
        expect(screen.getByText(/Overdue · 1/)).toBeInTheDocument();
        expect(screen.queryByText('Finished')).not.toBeInTheDocument();
        fireEvent.click(screen.getByText(/Done · 1/));
        expect(screen.getByText('Finished')).toBeInTheDocument();
    });

    it('shows the to-do ping count red and clears it once the list is shown', async () => {
        const api = makeApi();
        const refreshUnread = vi.fn();
        render(
            <MemoryRouter initialEntries={['/sub/todos']}>
                <TodosMobile api={api} unreadTodos={2} refreshUnread={refreshUnread} onOpenRelease={vi.fn()} />
            </MemoryRouter>,
        );
        await screen.findByText('Bring the lift');
        expect(screen.getByLabelText('2 new')).toHaveClass('alert');
        await waitFor(() => expect(api.markAllRead).toHaveBeenCalledWith({ types: ['checklist_assigned', 'checklist_due'] }));
        expect(refreshUnread).toHaveBeenCalled();
    });

    it('marks a to-do done through the adapter', async () => {
        const api = makeApi();
        render(
            <MemoryRouter initialEntries={['/sub/todos']}>
                <TodosMobile api={api} refreshUnread={vi.fn()} onOpenRelease={vi.fn()} />
            </MemoryRouter>,
        );
        const card = (await screen.findByText('Bring the lift')).closest('.sub-card');
        fireEvent.click(card.querySelector('button[aria-label="Mark done"]'));
        await waitFor(() => expect(api.setTodoStatus).toHaveBeenCalledWith(1, 'done'));
    });

    it('lists only mention-type rows on the Mentions segment and opens the release on tap', async () => {
        const api = makeApi();
        const onOpenRelease = vi.fn();
        render(
            <MemoryRouter initialEntries={['/sub/todos?seg=mentions']}>
                <TodosMobile api={api} refreshUnread={vi.fn()} onOpenRelease={onOpenRelease} />
            </MemoryRouter>,
        );
        await screen.findByText('Bill mentioned you');
        expect(screen.queryByText('New to-do')).not.toBeInTheDocument();  // a to-do ping is not a mention
        fireEvent.click(screen.getByText('Bill mentioned you'));
        await waitFor(() => expect(api.markRead).toHaveBeenCalledWith(11));
        expect(onOpenRelease).toHaveBeenCalledWith(9);
    });
});
