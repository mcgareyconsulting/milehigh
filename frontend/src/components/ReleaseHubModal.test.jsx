// The unified release modal: one dialog holding the release's details, the
// drawings/photos hub, the change log, and the notes rail. Covers the tab
// shell, the initialTab entry points, the dossier content, and the click-out
// margin that dismisses it.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { ReleaseHubModal } from './ReleaseHubModal.jsx';

// The details body fetches material orders; the drawings body fetches versions
// and photos; the rail fetches notes. None of those network shapes are under
// test here — the shell is.
vi.mock('../services/jobsApi', () => ({
    jobsApi: {
        getMaterialOrders: vi.fn(() => Promise.resolve({ orders: [] })),
        markMaterialOrderReceived: vi.fn(() => Promise.resolve({})),
        // The notes rail reads the update_notes event stream — the same feed the
        // Notes cell's history glyph used before it was folded into the modal.
        getNotesHistory: vi.fn(() => Promise.resolve({
            events: [
                {
                    id: 7,
                    action: 'update_notes',
                    user_name: 'Dave Cruz',
                    source: 'Brain',
                    created_at: '2026-07-19T12:46:16',
                    payload: { from: 'Fab has pack', to: 'Waiting on GC embed approval' },
                },
                {
                    id: 3,
                    action: 'update_notes',
                    user_name: 'Ryan Lopez',
                    source: 'Brain',
                    created_at: '2026-07-02T09:10:00',
                    payload: { from: '', to: 'Fab has pack' },
                },
                // A stage change must not leak into the notes rail.
                {
                    id: 4,
                    action: 'update_stage',
                    user_name: 'Ryan Lopez',
                    source: 'Brain',
                    created_at: '2026-07-03T09:10:00',
                    payload: { from: 'Cut Start', to: 'Cut Complete' },
                },
            ],
        })),
    },
}));
vi.mock('../services/notificationApi', () => ({
    fetchMentionableUsers: vi.fn(() => Promise.resolve([])),
}));
vi.mock('../utils/auth', () => ({
    checkAuth: vi.fn(() => Promise.resolve({ authenticated: true, user: { is_admin: false } })),
}));

// Shaped like a real Job Log row (app/brain/job_log/routes.py) — display keys
// for the table columns, raw keys for everything else.
const JOB = {
    id: 42,
    'Job #': '560',
    'Release #': '923',
    Job: 'Alta Metro',
    Description: 'Bldg C stair',
    Released: '2026-06-02',
    'Ship Date': '2026-07-28',
    'Start install': '2026-07-29',
    'Comp. ETA': '2026-08-01',
    Stage: 'Cut Complete',
    'Stage Group': 'FABRICATION',
    'Fab Order': 14,
    'Fab Hrs': 62,
    'Install HRS': 24,
    'Job Comp': null,
    Invoiced: null,
    PM: 'Doug',
    BY: 'Rich',
    installer: 'Team 2',
    num_guys: 3,
    'Paint color': 'Black',
    Notes: 'Waiting on GC embed approval',
    last_updated_at: '2026-07-19T12:46:16',
    source_of_update: 'Brain',
    trello_card_id: 'abc123',
    viewer_url: '',
};

beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ versions: [], photos: [], events: [] }),
    })));
});

afterEach(() => {
    vi.clearAllMocks();
});

const renderHub = (props = {}) => render(
    <ReleaseHubModal isOpen onClose={() => {}} job={JOB} releaseId={JOB.id} {...props} />
);

describe('ReleaseHubModal', () => {
    it('renders nothing when closed', () => {
        const { container } = render(
            <ReleaseHubModal isOpen={false} onClose={() => {}} job={JOB} releaseId={42} />
        );
        expect(container).toBeEmptyDOMElement();
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('heads itself with the id chip, description, stage pill, and context line', () => {
        renderHub();
        const dialog = screen.getByRole('dialog');
        expect(within(dialog).getByText('560-923')).toBeInTheDocument();
        expect(within(dialog).getByText('Bldg C stair')).toBeInTheDocument();
        // Stage appears twice: header pill and the Production field.
        expect(within(dialog).getAllByText('Cut Complete').length).toBeGreaterThanOrEqual(1);
        expect(within(dialog).getByText(/Alta Metro · PM Doug · Detailed by Rich/)).toBeInTheDocument();
    });

    it('offers all three tabs with Details active by default', () => {
        renderHub();
        expect(screen.getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'true');
        expect(screen.getByRole('tab', { name: 'Drawings & Photos' })).toHaveAttribute('aria-selected', 'false');
        expect(screen.getByRole('tab', { name: 'Change Log' })).toHaveAttribute('aria-selected', 'false');
    });

    it('opens straight to Drawings & Photos when asked', () => {
        renderHub({ initialTab: 'drawings' });
        expect(screen.getByRole('tab', { name: 'Drawings & Photos' })).toHaveAttribute('aria-selected', 'true');
        expect(screen.getByText('Drawings')).toBeInTheDocument();
    });

    it('drops the Drawings & Photos tab when no releaseId is available', () => {
        // A caller with only job/release digits (e.g. a Timeline material-order
        // chip whose release row is not loaded) cannot fetch versions/photos —
        // offering the tab would just render 404s.
        renderHub({ releaseId: null });
        expect(screen.queryByRole('tab', { name: 'Drawings & Photos' })).not.toBeInTheDocument();
        expect(screen.getByRole('tab', { name: 'Details' })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: 'Change Log' })).toBeInTheDocument();
    });

    it('switches tabs on click and keeps the visited pane mounted', () => {
        renderHub();
        expect(screen.getByText('Materials ordered')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('tab', { name: 'Drawings & Photos' }));
        expect(screen.getByRole('tab', { name: 'Drawings & Photos' })).toHaveAttribute('aria-selected', 'true');
        expect(screen.getByText('Drawings')).toBeInTheDocument();
        // Details stays in the DOM (hidden) so its state survives the switch.
        expect(screen.getByText('Materials ordered')).toBeInTheDocument();
    });

    it('lays the release out as a dossier, not three lonely facts', () => {
        renderHub();
        for (const heading of ['Schedule', 'Production', 'Assignment', 'Materials ordered', 'Stage progress']) {
            expect(screen.getByText(heading)).toBeInTheDocument();
        }
    });

    it('renders the release fields the Job Log row carries', () => {
        renderHub();
        const dialog = screen.getByRole('dialog');
        // Schedule dates are reformatted from ISO.
        expect(within(dialog).getByText('Jun 2, 2026')).toBeInTheDocument();
        expect(within(dialog).getByText('Aug 1, 2026')).toBeInTheDocument();
        // Production + assignment.
        expect(within(dialog).getByText('14')).toBeInTheDocument();
        expect(within(dialog).getByText('Rich')).toBeInTheDocument();
        expect(within(dialog).getByText('Team 2')).toBeInTheDocument();
        expect(within(dialog).getByText('Black')).toBeInTheDocument();
    });

    it('shows an em dash for empty fields rather than dropping the row', () => {
        renderHub();
        const dialog = screen.getByRole('dialog');
        // Job Comp and Invoiced are null on this release.
        expect(within(dialog).getAllByText('—').length).toBeGreaterThanOrEqual(2);
    });

    it('flags an ASAP install with the mini-flag beside the date', () => {
        renderHub({ job: { ...JOB, start_install_asap: true } });
        const dialog = screen.getByRole('dialog');
        // The flag chip and the value both read ASAP.
        expect(within(dialog).getAllByText('ASAP').length).toBeGreaterThanOrEqual(1);
    });

    it('flags a hard start-install date', () => {
        renderHub({ job: { ...JOB, start_install_formulaTF: false } });
        expect(screen.getByText('HARD')).toBeInTheDocument();
    });

    it('walks the real stage ladder, not the shortened prototype one', () => {
        renderHub();
        const dialog = screen.getByRole('dialog');
        // Stages the handoff prototype's 10-step ladder drops entirely.
        for (const stage of ['Material Ordered', 'Cut Start', 'Store at MHMW']) {
            expect(within(dialog).getByTitle(stage)).toBeInTheDocument();
        }
    });

    it('puts the external links in the header, enabled only when there is a target', () => {
        renderHub();
        // Trello card id is present → real link; no Procore ids and no viewer_url → inert.
        expect(screen.getByText('Trello').tagName).toBe('A');
        expect(screen.getByText('Procore').tagName).not.toBe('A');
    });

    it('renders the notes history newest-first, badging the current note', async () => {
        renderHub();
        expect(screen.getByText('Notes')).toBeInTheDocument();

        expect(await screen.findByText('Waiting on GC embed approval')).toBeInTheDocument();
        expect(screen.getByText('Fab has pack')).toBeInTheDocument();
        // The newest event matches the release's Notes field, so it carries the
        // badge rather than the text being printed twice.
        expect(screen.getByText('Current')).toBeInTheDocument();
        expect(screen.getAllByText('Waiting on GC embed approval')).toHaveLength(1);
    });

    it('keeps non-notes events out of the notes rail', async () => {
        renderHub();
        await screen.findByText('Fab has pack');
        expect(screen.queryByText('Cut Complete — from Cut Start')).not.toBeInTheDocument();
        // Two update_notes events, so two authors; the stage change contributes none.
        expect(screen.getByText('Dave Cruz')).toBeInTheDocument();
        expect(screen.getByText('Ryan Lopez')).toBeInTheDocument();
    });

    it('points at the Job Log cell as the place notes are edited', () => {
        renderHub();
        expect(screen.getByText(/edited in the Job Log's Notes column/)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: /Post note/ })).not.toBeInTheDocument();
    });

    it('closes on the backdrop, on the × button, and on Escape', () => {
        const onClose = vi.fn();
        renderHub({ onClose });

        // Portaled to document.body, so the backdrop is the panel's parent —
        // the click-out margin around the panel is what makes it reachable.
        const backdrop = screen.getByRole('dialog').parentElement;
        fireEvent.click(backdrop);
        expect(onClose).toHaveBeenCalledTimes(1);

        fireEvent.click(screen.getByLabelText('Close'));
        expect(onClose).toHaveBeenCalledTimes(2);

        fireEvent.keyDown(window, { key: 'Escape' });
        expect(onClose).toHaveBeenCalledTimes(3);
    });

    it('does not close when the panel itself is clicked', () => {
        const onClose = vi.fn();
        renderHub({ onClose });
        fireEvent.click(screen.getByRole('dialog'));
        expect(onClose).not.toHaveBeenCalled();
    });
});
