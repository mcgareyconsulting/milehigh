// Paint Color on the Archive table uses the same Excel-style header dropdown as
// the Job Log. These tests drive that control: multi-select, blanks, chips,
// sort, and the archive-only localStorage keys.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../utils/auth', () => ({
    checkAuth: vi.fn(),
}));

vi.mock('../services/jobsApi', () => ({
    jobsApi: {
        fetchAllJobs: vi.fn(),
        unarchiveRelease: vi.fn(),
    },
}));

vi.mock('../components/ReleaseHubModal', () => ({ ReleaseHubModal: () => null }));
vi.mock('../components/PdfMarkupModal', () => ({ PdfMarkupModal: () => null }));

vi.mock('../components/JobsTableRow', () => ({
    JobsTableRow: ({ row }) => (
        <tr>
            <td>{row.Description}</td>
        </tr>
    ),
}));

vi.mock('../components/JobLogCardGrid', () => ({
    default: ({ jobs }) => (
        <ul aria-label="cards">
            {jobs.map((job) => <li key={job.id}>{job.Description}</li>)}
        </ul>
    ),
}));

import Archive from './Archive.jsx';
import { checkAuth } from '../utils/auth';
import { jobsApi } from '../services/jobsApi';

function job({ id, jobNum, release, project, description, paint }) {
    return {
        id,
        'Job #': jobNum,
        'Release #': release,
        Job: project,
        Description: description,
        'Fab Hrs': 1,
        'Install HRS': 1,
        'Paint color': paint,
        PM: 'A',
        BY: 'B',
        Released: '2024-01-01',
        'Fab Order': 3,
        Stage: 'Complete',
        'Start install': null,
        'Comp. ETA': null,
        'Job Comp': 'X',
        Invoiced: 'X',
        Notes: '',
    };
}

// Input order is deliberately not the display order. Default sort is Job # then Release #.
const JOBS = [
    job({ id: 4, jobNum: 400, release: '1', project: 'Gamma', description: 'Zinc late', paint: 'Zinc' }),
    job({ id: 1, jobNum: 100, release: '1', project: 'Alpha', description: 'Alpha red', paint: 'Red' }),
    job({ id: 6, jobNum: 300, release: '2', project: 'Beta', description: 'Bare empty', paint: '   ' }),
    job({ id: 3, jobNum: 200, release: '1', project: 'Beta', description: 'Beta blue', paint: 'Blue' }),
    job({ id: 2, jobNum: 100, release: '2', project: 'Alpha', description: 'Alpha red trim', paint: '  Red  ' }),
    job({ id: 5, jobNum: 300, release: '1', project: 'Beta', description: 'Bare null', paint: null }),
];

const JOB_NUMBER_ORDER = [
    'Alpha red',
    'Alpha red trim',
    'Beta blue',
    'Bare null',
    'Bare empty',
    'Zinc late',
];

// Vitest may ship a non-functional localStorage (the global exists, but it is
// undefined until Node is started with --localstorage-file). Same stub the
// role-flag tests use so getItem/setItem/clear are real.
function installMemoryLocalStorage() {
    const store = new Map();
    vi.stubGlobal('localStorage', {
        getItem: (k) => (store.has(k) ? store.get(k) : null),
        setItem: (k, v) => { store.set(String(k), String(v)); },
        removeItem: (k) => { store.delete(k); },
        clear: () => { store.clear(); },
    });
}

function renderArchive() {
    return render(
        <MemoryRouter>
            <Archive />
        </MemoryRouter>
    );
}

function paintHeader() {
    return screen.getByRole('button', { name: /^Paint Color$/ });
}

function visibleDescriptions() {
    return screen.getAllByRole('row').slice(1).map((row) => row.textContent);
}

async function renderTable() {
    renderArchive();
    expect(await screen.findByText('Alpha red')).toBeInTheDocument();
    expect(paintHeader()).toBeInTheDocument();
}

describe('Archive paint color header filter', () => {
    beforeEach(() => {
        installMemoryLocalStorage();
        localStorage.setItem('ar_view', 'table');
        // A live Job Log filter must not leak into Archive, and Archive must not rewrite it.
        localStorage.setItem('jl_column_filters', JSON.stringify({ Stage: ['Complete'] }));
        localStorage.setItem('jl_column_sort', JSON.stringify({ column: 'Paint color', direction: 'desc' }));
        vi.clearAllMocks();
        checkAuth.mockResolvedValue({ is_admin: false });
        jobsApi.fetchAllJobs.mockResolvedValue(JOBS);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('filters to the checked colors, keeps every color in the list, and trims duplicates', async () => {
        const user = userEvent.setup();
        await renderTable();
        expect(visibleDescriptions()).toEqual(JOB_NUMBER_ORDER);

        await user.click(paintHeader());
        // "  Red  " and "Red" are one choice.
        expect(screen.getAllByRole('checkbox', { name: /^Red$/ })).toHaveLength(1);
        expect(screen.getByRole('checkbox', { name: /^Blue$/ })).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: /^\(Blanks\)$/ })).toBeInTheDocument();

        await user.click(screen.getByRole('checkbox', { name: /^Red$/ }));
        await user.click(screen.getByRole('checkbox', { name: /^Blue$/ }));
        await user.click(screen.getByRole('button', { name: 'Apply' }));

        expect(visibleDescriptions()).toEqual(['Alpha red', 'Alpha red trim', 'Beta blue']);
        expect(screen.getByText('Paint Color: Red')).toBeInTheDocument();
        expect(screen.getByText('Paint Color: Blue')).toBeInTheDocument();
        expect(JSON.parse(localStorage.getItem('ar_column_filters'))).toEqual({
            'Paint color': ['Red', 'Blue'],
        });
        expect(JSON.parse(localStorage.getItem('jl_column_filters'))).toEqual({ Stage: ['Complete'] });

        // Excel narrowing: the choice just applied does not remove the other colors.
        await user.click(paintHeader());
        expect(screen.getByRole('checkbox', { name: /^Zinc$/ })).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: /^\(Blanks\)$/ })).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: /^Red$/ })).toBeChecked();
        expect(screen.getByRole('checkbox', { name: /^Blue$/ })).toBeChecked();
    });

    it('treats an empty paint color as (Blanks)', async () => {
        const user = userEvent.setup();
        await renderTable();

        await user.click(paintHeader());
        await user.click(screen.getByRole('checkbox', { name: /^\(Blanks\)$/ }));
        await user.click(screen.getByRole('button', { name: 'Apply' }));

        expect(visibleDescriptions()).toEqual(['Bare null', 'Bare empty']);
        expect(screen.getByText('Paint Color: (Blanks)')).toBeInTheDocument();
    });

    it('removes one color from its chip and Reset Filters clears the archive filter only', async () => {
        const user = userEvent.setup();
        await renderTable();

        await user.click(paintHeader());
        await user.click(screen.getByRole('checkbox', { name: /^Red$/ }));
        await user.click(screen.getByRole('checkbox', { name: /^Blue$/ }));
        await user.click(screen.getByRole('button', { name: 'Apply' }));

        await user.click(screen.getByRole('button', { name: 'Remove Paint Color filter Red' }));
        expect(visibleDescriptions()).toEqual(['Beta blue']);
        expect(screen.queryByText('Paint Color: Red')).not.toBeInTheDocument();
        expect(JSON.parse(localStorage.getItem('ar_column_filters'))).toEqual({
            'Paint color': ['Blue'],
        });

        await user.click(screen.getByRole('button', { name: 'Reset Filters' }));
        expect(visibleDescriptions()).toEqual(JOB_NUMBER_ORDER);
        expect(screen.queryByText(/Paint Color:/)).not.toBeInTheDocument();
        expect(localStorage.getItem('ar_column_filters')).toBeNull();
        expect(JSON.parse(localStorage.getItem('jl_column_filters'))).toEqual({ Stage: ['Complete'] });
        expect(JSON.parse(localStorage.getItem('jl_column_sort'))).toEqual({
            column: 'Paint color',
            direction: 'desc',
        });
    });

    it('sorts A→Z and Z→A from the header, with blanks last, and Clear restores job order', async () => {
        const user = userEvent.setup();
        await renderTable();

        await user.click(paintHeader());
        await user.click(screen.getByRole('button', { name: 'Sort A→Z' }));
        // Sort compares the raw cell text. "  Red  " still filters as Red, but the
        // leading spaces sort ahead of letters. Blanks stay last in either direction.
        expect(visibleDescriptions()).toEqual([
            'Alpha red trim',
            'Beta blue',
            'Alpha red',
            'Zinc late',
            'Bare null',
            'Bare empty',
        ]);
        expect(JSON.parse(localStorage.getItem('ar_column_sort'))).toEqual({
            column: 'Paint color',
            direction: 'asc',
        });
        expect(JSON.parse(localStorage.getItem('jl_column_sort'))).toEqual({
            column: 'Paint color',
            direction: 'desc',
        });

        await user.click(screen.getByRole('button', { name: 'Sort Z→A' }));
        expect(visibleDescriptions()).toEqual([
            'Zinc late',
            'Alpha red',
            'Beta blue',
            'Alpha red trim',
            'Bare null',
            'Bare empty',
        ]);

        await user.click(screen.getByRole('button', { name: 'Clear' }));
        expect(visibleDescriptions()).toEqual(JOB_NUMBER_ORDER);
        expect(localStorage.getItem('ar_column_sort')).toBeNull();
    });

    it('reapplies a saved archive filter on load, including in card view', async () => {
        localStorage.setItem('ar_column_filters', JSON.stringify({ 'Paint color': ['Zinc'] }));
        const table = renderArchive();
        expect(await screen.findByText('Zinc late')).toBeInTheDocument();
        expect(visibleDescriptions()).toEqual(['Zinc late']);
        expect(screen.getByText('Paint Color: Zinc')).toBeInTheDocument();
        table.unmount();

        localStorage.setItem('ar_view', 'cards');
        renderArchive();
        const cards = await screen.findByRole('list', { name: 'cards' });
        expect(cards).toHaveTextContent('Zinc late');
        expect(cards).not.toHaveTextContent('Alpha red');
        expect(screen.queryByRole('button', { name: /^Paint Color$/ })).not.toBeInTheDocument();
    });

    it('lists only colors reachable under the project buttons and the page search', async () => {
        const user = userEvent.setup();
        await renderTable();

        await user.click(screen.getByRole('button', { name: /^Alpha$/ }));
        expect(visibleDescriptions()).toEqual(['Alpha red', 'Alpha red trim']);

        await user.click(paintHeader());
        expect(screen.getByRole('checkbox', { name: /^Red$/ })).toBeInTheDocument();
        expect(screen.queryByRole('checkbox', { name: /^Blue$/ })).not.toBeInTheDocument();
        expect(screen.queryByRole('checkbox', { name: /^Zinc$/ })).not.toBeInTheDocument();
        expect(screen.queryByRole('checkbox', { name: /^\(Blanks\)$/ })).not.toBeInTheDocument();

        await user.click(screen.getByRole('button', { name: /^All$/ }));
        await user.type(
            screen.getByPlaceholderText('Job #, release, name, description...'),
            'Beta',
        );
        await user.click(paintHeader());
        expect(screen.getByRole('checkbox', { name: /^Blue$/ })).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: /^\(Blanks\)$/ })).toBeInTheDocument();
        expect(screen.queryByRole('checkbox', { name: /^Red$/ })).not.toBeInTheDocument();
        expect(screen.queryByRole('checkbox', { name: /^Zinc$/ })).not.toBeInTheDocument();
        expect(visibleDescriptions()).toEqual(['Beta blue', 'Bare null', 'Bare empty']);
    });
});
