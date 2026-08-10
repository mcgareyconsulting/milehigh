import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import axios from 'axios';
import EventsList, { fieldLabelForAction, fromToOf } from './EventsList.jsx';

vi.mock('axios', () => ({
    default: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

const EVENTS = [
    {
        id: 1,
        type: 'job',
        action: 'update_stage',
        user_name: 'David Servold',
        source: 'Brain',
        created_at: '2026-04-16T07:00:00',
        job: 340,
        release: '481',
        payload: { from: 'Paint complete', to: 'Shipping completed' },
        current_value: 'Shipping completed',
    },
    {
        id: 2,
        type: 'job',
        action: 'update_fab_order',
        user_name: 'David Servold',
        source: 'Brain',
        created_at: '2026-04-16T07:00:30',
        job: 340,
        release: '481',
        payload: { from: 3, to: 1 },
        current_value: 1,
    },
    {
        id: 3,
        type: 'job',
        action: 'update_notes',
        user_name: 'Bill ONeill',
        source: 'Brain',
        created_at: '2026-04-30T06:53:00',
        job: 340,
        release: '481',
        payload: { from: '', to: 'Need to paint and ship clevis rods.' },
        current_value: 'Need to paint and ship clevis rods.',
    },
];

describe('fieldLabelForAction / fromToOf', () => {
    it('maps raw actions to plain labels', () => {
        expect(fieldLabelForAction('update_fab_order')).toBe('Fab Order');
        expect(fieldLabelForAction('update_stage')).toBe('Stage');
        expect(fieldLabelForAction('update_notes')).toBe('Notes');
        expect(fieldLabelForAction('update_ship_date')).toBe('Ship Date');
        expect(fieldLabelForAction('update_something_else')).toBe('Something Else');
    });

    it('extracts from/to from job payloads', () => {
        expect(fromToOf(EVENTS[0])).toEqual({ from: 'Paint complete', to: 'Shipping completed' });
    });
});

describe('EventsList variant=hub', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        axios.get.mockResolvedValue({ data: { events: EVENTS } });
    });

    it('renders summary, day groups, field labels, and no Identifier column', async () => {
        render(
            <EventsList
                variant="hub"
                jobFilter="340"
                releaseFilter="481"
            />
        );

        expect(await screen.findByText('3 changes')).toBeInTheDocument();
        expect(screen.getByText('Newest first')).toBeInTheDocument();
        expect(screen.getByText('Stage')).toBeInTheDocument();
        expect(screen.getByText('Fab Order')).toBeInTheDocument();
        expect(screen.getByText('Notes')).toBeInTheDocument();

        expect(screen.getByText('Paint complete')).toBeInTheDocument();
        expect(screen.getByText('Shipping completed')).toBeInTheDocument();

        expect(screen.queryByText('Identifier')).not.toBeInTheDocument();
        expect(screen.queryByText('update_stage')).not.toBeInTheDocument();
        expect(screen.queryByText('update_fab_order')).not.toBeInTheDocument();

        expect(screen.getAllByText('Brain').length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByRole('button', { name: /Undo/i }).length).toBeGreaterThanOrEqual(1);
    });

    it('does not use hub layout for default variant', async () => {
        render(
            <EventsList
                jobFilter="340"
                releaseFilter="481"
            />
        );

        expect(await screen.findByText('Identifier')).toBeInTheDocument();
        expect(screen.getByText('update_stage')).toBeInTheDocument();
    });

    it('expands payload on toggle', async () => {
        render(
            <EventsList
                variant="hub"
                jobFilter="340"
                releaseFilter="481"
            />
        );

        expect(await screen.findByText('3 changes')).toBeInTheDocument();

        const toggles = screen.getAllByText(/payload/);
        fireEvent.click(toggles[0]);
        await waitFor(() => {
            expect(screen.getByText(/"from"/)).toBeInTheDocument();
        });
    });
});
