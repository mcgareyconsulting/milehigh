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
        updateNotes: vi.fn(() => Promise.resolve({})),
        getBBReview: vi.fn(() => Promise.resolve(null)),
        requestBBReview: vi.fn(() => Promise.resolve({ status: 'pending' })),
        // Activity rail reads the release event stream (notes + stage/date/fab).
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
                {
                    id: 4,
                    action: 'update_stage',
                    user_name: 'Ryan Lopez',
                    source: 'Brain',
                    created_at: '2026-07-03T09:10:00',
                    payload: { from: 'Cut Start', to: 'Cut Complete' },
                },
                {
                    id: 5,
                    action: 'update_ship_date',
                    user_name: 'Dave Cruz',
                    source: 'Brain',
                    created_at: '2026-07-04T11:00:00',
                    payload: { from: null, to: '2026-07-28' },
                },
                {
                    id: 6,
                    action: 'update_fab_order',
                    user_name: 'Ryan Lopez',
                    source: 'Brain',
                    created_at: '2026-07-03T09:10:30',
                    payload: { from: 5, to: 3 },
                },
            ],
        })),
    },
}));
vi.mock('../services/notificationApi', () => ({
    fetchMentionableUsers: vi.fn(() => Promise.resolve([])),
}));
vi.mock('../utils/auth', () => ({
    // /api/auth/me shape — admin/drafter flags at top level.
    checkAuth: vi.fn(() => Promise.resolve({ is_admin: true, is_drafter: true })),
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
        expect(screen.getByRole('tab', { name: 'Attachments' })).toHaveAttribute('aria-selected', 'false');
        expect(screen.getByRole('tab', { name: 'Change Log' })).toHaveAttribute('aria-selected', 'false');
    });

    it('opens straight to Attachments when asked (legacy drawings key still works)', async () => {
        renderHub({ initialTab: 'drawings' });
        expect(screen.getByRole('tab', { name: 'Attachments' })).toHaveAttribute('aria-selected', 'true');
        // Embedded split pane: left rail Drawings section + empty viewer prompt.
        expect(await screen.findByText('Drawings')).toBeInTheDocument();
        expect(screen.getByText('+ Upload PDF')).toBeInTheDocument();
        expect(screen.getByText('Photos')).toBeInTheDocument();
        // Empty release: left rail empty-state and/or right viewer prompt.
        expect(
            screen.getAllByText(/No drawings yet|Select a drawing to preview/i).length,
        ).toBeGreaterThanOrEqual(1);
    });

    it('drops the Attachments tab when no releaseId is available', () => {
        // A caller with only job/release digits (e.g. a Timeline material-order
        // chip whose release row is not loaded) cannot fetch versions/photos —
        // offering the tab would just render 404s.
        renderHub({ releaseId: null });
        expect(screen.queryByRole('tab', { name: 'Attachments' })).not.toBeInTheDocument();
        expect(screen.getByRole('tab', { name: 'Details' })).toBeInTheDocument();
        expect(screen.getByRole('tab', { name: 'Change Log' })).toBeInTheDocument();
    });

    it('switches tabs on click and keeps the visited pane mounted', () => {
        renderHub();
        expect(screen.getByText('Materials ordered')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('tab', { name: 'Attachments' }));
        expect(screen.getByRole('tab', { name: 'Attachments' })).toHaveAttribute('aria-selected', 'true');
        expect(screen.getByText('Drawings')).toBeInTheDocument();
        // Details stays in the DOM (hidden) so its state survives the switch.
        expect(screen.getByText('Materials ordered')).toBeInTheDocument();
    });

    it('hides the Activity rail on Attachments and shows it on Details', () => {
        renderHub();
        expect(screen.getByText('Activity')).toBeInTheDocument();

        fireEvent.click(screen.getByRole('tab', { name: 'Attachments' }));
        expect(screen.queryByText('Activity')).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole('tab', { name: 'Details' }));
        expect(screen.getByText('Activity')).toBeInTheDocument();
    });

    it('shows an amber findings badge on Attachments when count > 0', () => {
        renderHub({ attachmentsBadgeCount: 8 });
        const tab = screen.getByRole('tab', { name: /Attachments/ });
        expect(within(tab).getByText('8')).toBeInTheDocument();
    });

    it('hides the findings badge when count is 0', () => {
        renderHub({ attachmentsBadgeCount: 0 });
        const tab = screen.getByRole('tab', { name: 'Attachments' });
        expect(within(tab).queryByText('0')).not.toBeInTheDocument();
    });

    it('lays the release out as date hero + 3-col metadata + stage progress', () => {
        renderHub();
        // Date-flow hero labels (Install Prog also labels the Production field).
        for (const label of ['Released', 'Ship Date', 'Start Install', 'Comp. ETA']) {
            expect(screen.getByText(label)).toBeInTheDocument();
        }
        expect(screen.getAllByText('Install Prog').length).toBeGreaterThanOrEqual(1);
        for (const heading of ['Production', 'Assignment', 'Materials ordered', 'Stage progress']) {
            expect(screen.getByText(heading)).toBeInTheDocument();
        }
        // Schedule is no longer a section — dates live in the hero only.
        expect(screen.queryByText('Schedule')).not.toBeInTheDocument();
    });

    it('renders the banana-code icon row instead of the 17-segment progress bar', () => {
        renderHub();
        // StageIconRow exposes each department as an img alt like "Cut yellow".
        expect(screen.getByAltText(/Admin/i)).toBeInTheDocument();
        expect(screen.getByAltText(/Install/i)).toBeInTheDocument();
    });

    it('intermingles stage/date/fab updates with notes on the Activity rail', async () => {
        renderHub();
        // Stage chips + merged fab (same user/minute as stage) + ship + notes.
        // Stage chips (also appears as header/Production stage pill — use getAll).
        expect(await screen.findByText(/also Fab Order 5 → 3/)).toBeInTheDocument();
        expect(screen.getAllByText('Cut Complete').length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText('Cut Start').length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText(/Ship date set to/)).toBeInTheDocument();
        expect(screen.getByText('Waiting on GC embed approval')).toBeInTheDocument();
        expect(screen.getAllByText('Note').length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText('Activity')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: '+ Note' })).toBeInTheDocument();
    });

    it('renders the release fields the Job Log row carries', () => {
        renderHub();
        const dialog = screen.getByRole('dialog');
        // Hero dates are reformatted from ISO.
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
        // Job Comp / Install Prog and Invoiced are null on this release.
        expect(within(dialog).getAllByText('—').length).toBeGreaterThanOrEqual(2);
    });

    it('appends % to whole-number Install Prog', () => {
        renderHub({ job: { ...JOB, 'Job Comp': 75 } });
        const dialog = screen.getByRole('dialog');
        // Hero + Production field both show 75%.
        expect(within(dialog).getAllByText('75%').length).toBeGreaterThanOrEqual(1);
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

    it('renders banana-code department icons for stage progress', () => {
        renderHub();
        // Banana Code uses department alts (Admin…Install), not per-stage titles.
        expect(screen.getByAltText(/Admin/i)).toBeInTheDocument();
        expect(screen.getByAltText(/Cut/i)).toBeInTheDocument();
        expect(screen.getByAltText(/Install/i)).toBeInTheDocument();
    });

    it('puts the external links in the header, enabled only when there is a target', () => {
        renderHub();
        // Trello card id is present → real link; no Procore ids and no viewer_url → inert.
        expect(screen.getByText('Trello').tagName).toBe('A');
        expect(screen.getByText('Procore').tagName).not.toBe('A');
    });

    it('renders notes history newest-first on the Activity rail', async () => {
        renderHub();
        expect(screen.getByText('Activity')).toBeInTheDocument();

        expect(await screen.findByText('Waiting on GC embed approval')).toBeInTheDocument();
        expect(screen.getByText('Fab has pack')).toBeInTheDocument();
        // Newest note matches the release Notes field once (not duplicated as orphan).
        expect(screen.getAllByText('Waiting on GC embed approval')).toHaveLength(1);
    });

    it('shows stage/date authors on the Activity rail alongside note authors', async () => {
        renderHub();
        await screen.findByText('Fab has pack');
        expect(screen.getAllByText('Dave Cruz').length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText('Ryan Lopez').length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText('Cut Complete').length).toBeGreaterThanOrEqual(1);
    });

    it('points at the Change Log for full undo history', () => {
        renderHub();
        expect(screen.getByText(/full undo history is on the Change Log tab/i)).toBeInTheDocument();
    });

    it('opens a note composer from + Note', async () => {
        renderHub();
        fireEvent.click(screen.getByRole('button', { name: '+ Note' }));
        expect(screen.getByPlaceholderText(/Overwrite Job Log notes/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Save note' })).toBeInTheDocument();
    });

    it('opens Change Log with hub layout (no Identifier table)', async () => {
        // EventsList fetches via axios; stub a small list for the hub pane.
        const axios = (await import('axios')).default;
        if (axios.get && typeof axios.get.mockResolvedValue === 'function') {
            axios.get.mockResolvedValue({
                data: {
                    events: [{
                        id: 1,
                        type: 'job',
                        action: 'update_stage',
                        user_name: 'Ryan',
                        source: 'Brain',
                        created_at: '2026-07-03T09:10:00',
                        job: 560,
                        release: '923',
                        payload: { from: 'Cut Start', to: 'Cut Complete' },
                        current_value: 'Cut Complete',
                    }],
                },
            });
        }
        renderHub();
        fireEvent.click(screen.getByRole('tab', { name: 'Change Log' }));
        // Hub summary or loading — either means the pane mounted without Identifier.
        expect(screen.queryByText('Identifier')).not.toBeInTheDocument();
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
