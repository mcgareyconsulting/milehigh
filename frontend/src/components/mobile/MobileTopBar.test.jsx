import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MobileTopBar from './MobileTopBar';

const tabs = [
    { to: '/m/todos', label: 'To-Dos', badge: 3 },
    { to: '/m/job-log', label: 'Job Log' },
    { to: '/m/tm-tickets', label: 'T&M' },
];

describe('MobileTopBar', () => {
    it('renders label-only tabs, marks the active one and shows the red count inline', () => {
        render(<MemoryRouter initialEntries={['/m/job-log']}><MobileTopBar tabs={tabs} onMenu={() => {}} /></MemoryRouter>);
        expect(screen.getByText('Job Log').closest('a')).toHaveClass('active');
        expect(screen.getByText('To-Dos').closest('a')).not.toHaveClass('active');
        expect(screen.getByLabelText('3 unread')).toHaveTextContent('3');
        expect(screen.queryByRole('img', { hidden: true })).toBeTruthy(); // the Brain mark
    });

    it('caps the badge at 99+ and hides it at zero', () => {
        render(<MemoryRouter><MobileTopBar tabs={[{ to: '/a', label: 'A', badge: 250 }, { to: '/b', label: 'B', badge: 0 }]} onMenu={() => {}} /></MemoryRouter>);
        expect(screen.getByLabelText('250 unread')).toHaveTextContent('99+');
        expect(screen.queryByLabelText('0 unread')).not.toBeInTheDocument();
    });

    it('opens the menu', () => {
        const onMenu = vi.fn();
        render(<MemoryRouter><MobileTopBar tabs={tabs} onMenu={onMenu} /></MemoryRouter>);
        fireEvent.click(screen.getByLabelText('Menu'));
        expect(onMenu).toHaveBeenCalled();
    });
});
