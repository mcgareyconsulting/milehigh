// BUG-14: the release hub is hosted on JobLogContent, which stays mounted
// when effectiveView flips cards ↔ table (the iPad-rotate remount). Opening
// from cards and then switching to table must leave the dialog up.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, Outlet } from 'react-router-dom';
import JobLogContent from './JobLogContent.jsx';

vi.mock('../components/ReleaseHubModal', () => ({
    ReleaseHubModal: ({ isOpen, job }) => (
        isOpen && job ? <div role="dialog">{job.Description}</div> : null
    ),
}));
vi.mock('../components/PdfMarkupModal', () => ({ PdfMarkupModal: () => null }));
vi.mock('../components/PdfVersionHistoryModal', () => ({ PdfVersionHistoryModal: () => null }));
vi.mock('../components/ColumnHeaderFilter', () => ({ default: ({ children }) => <span>{children}</span> }));
vi.mock('../components/JobLogCardGrid', () => ({
    default: ({ jobs, onOpenHub }) => (
        <button type="button" onClick={() => onOpenHub(jobs[0], 'details')}>Open card hub</button>
    ),
}));
vi.mock('../components/JobsTableRow', () => ({
    JobsTableRow: ({ row, onOpenReleaseHub }) => (
        <button type="button" onClick={() => onOpenReleaseHub(row, 'details')}>Open row hub</button>
    ),
}));

const JOB = {
    id: 42,
    'Job #': 500,
    'Release #': '1',
    Job: 'Novel',
    Description: 'Stair 1',
    Stage: 'Released',
};

function ctx(effectiveView) {
    return {
        loading: false,
        fetchError: null,
        effectiveView,
        renderRows: [JOB],
        secondarySearchResults: [],
        search: '',
        jumpToTarget: null,
        stageToGroup: {},
        stageGroupColors: {},
        stageGroupDupColors: null,
        duplicateFabOrders: null,
        hasJobsData: true,
        refetch: vi.fn(),
        handleCascadeRecalculating: vi.fn(),
        columnHeaders: ['Job #', 'Release #', 'Description'],
        columnWidthPercents: { 'Job #': 20, 'Release #': 20, Description: 60 },
        isDesktop: effectiveView === 'table',
        uniqueValuesByColumn: {},
        columnFilters: {},
        columnSort: {},
        setColumnFilter: vi.fn(),
        setColumnSort: vi.fn(),
        isAdmin: true,
        isDrafter: true,
        isOldMan: false,
        handleDeleteJob: vi.fn(),
    };
}

function Layout({ view }) {
    return <Outlet context={ctx(view)} />;
}

function Harness() {
    const [view, setView] = useState('cards');
    return (
        <>
            <button type="button" onClick={() => setView('table')}>Rotate to table</button>
            <MemoryRouter initialEntries={['/']}>
                <Routes>
                    <Route element={<Layout view={view} />}>
                        <Route path="/" element={<JobLogContent />} />
                    </Route>
                </Routes>
            </MemoryRouter>
        </>
    );
}

describe('JobLogContent hosted hub survives the view swap', () => {
    beforeEach(() => {
        sessionStorage.clear();
    });

    it('stays open after cards → table (the iPad landscape remount)', async () => {
        const user = userEvent.setup();
        render(<Harness />);
        await user.click(screen.getByRole('button', { name: 'Open card hub' }));
        expect(screen.getByRole('dialog')).toHaveTextContent('Stair 1');
        expect(JSON.parse(sessionStorage.getItem('mhmw_open_dialog:jl_hub'))).toEqual({
            id: 42,
            tab: 'details',
            scrollToMaterials: false,
        });

        await user.click(screen.getByRole('button', { name: 'Rotate to table' }));
        expect(screen.getByRole('dialog')).toHaveTextContent('Stair 1');
        expect(screen.getByRole('button', { name: 'Open row hub' })).toBeInTheDocument();
    });
});
