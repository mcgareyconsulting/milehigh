// One document hub per splice family (T9): the Attachments viewer lists the original's and
// every splice's files together, grouped by the release each is attached to — and every
// per-file call (comments, Carmen review, the markup canvas, the ↗ window) goes through
// the release that OWNS the file, never the row that happens to be open. A new upload
// joins the open release's own chain.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { PdfViewerPane } from './PdfViewerPane.jsx';
import { jobsApi } from '../../services/jobsApi';

vi.mock('../../services/jobsApi', () => ({
    jobsApi: {
        getBBReview: vi.fn(() => Promise.resolve(null)),
        getVersionComments: vi.fn(() => Promise.resolve([])),
        addVersionComment: vi.fn(() => Promise.resolve({ id: 9, body: 'hi' })),
    },
}));
vi.mock('../../services/notificationApi', () => ({
    fetchMentionableUsers: vi.fn(() => Promise.resolve([])),
}));
vi.mock('../../utils/auth', () => ({
    checkAuth: vi.fn(() => Promise.resolve({ is_admin: true, is_drafter: true })),
}));
// The canvas and dock have their own suites; here they only report which release they got.
vi.mock('../PdfMarkupModal', () => ({
    PdfMarkupModal: ({ releaseId, versionId }) => (
        <div data-testid="canvas">canvas {releaseId}/{versionId}</div>
    ),
}));
vi.mock('./ViewerDock', () => ({
    ViewerDock: ({ releaseId, onCommentDraft, onSubmitComment }) => (
        <div data-testid="dock">
            dock {releaseId}
            <button type="button" onClick={() => onCommentDraft('hi')}>draft</button>
            <button type="button" onClick={onSubmitComment}>send</button>
        </div>
    ),
}));
vi.mock('./ProcorePullDialog', () => ({ ProcorePullDialog: () => null }));

// 340-666 (id 1) with splice 340-666.1 (id 2). The server returns the original first,
// newest version first within each release.
const v = (id, releaseId, label, n, name, isSplice) => ({
    id, release_id: releaseId, release_label: label, is_splice: isSplice,
    version_number: n, original_filename: name, uploaded_at: '2026-09-20T10:00:00',
    uploaded_by: { id: 1, name: 'Dana' }, file_size_bytes: 1000,
});
const FAMILY_PAYLOAD = {
    release_id: 2,
    versions: [
        v(11, 1, '340-666', 2, 'parent-v2.pdf', false),
        v(10, 1, '340-666', 1, 'parent.pdf', false),
        v(20, 2, '340-666.1', 1, 'splice.pdf', true),
    ],
    family: [
        { release_id: 1, release_label: '340-666', is_splice: false, is_archived: false },
        { release_id: 2, release_label: '340-666.1', is_splice: true, is_archived: false },
    ],
};

let fetchMock;
beforeEach(() => {
    fetchMock = vi.fn((url, opts) => {
        if (opts?.method === 'POST') {
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 21 }) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve(FAMILY_PAYLOAD) });
    });
    vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
});

const openMenu = () => fireEvent.click(screen.getByRole('button', { expanded: false, name: /pdf/i }));

describe('PdfViewerPane — splice family hub', () => {
    it('asks for the whole family, from whichever member is open', async () => {
        render(<PdfViewerPane releaseId={2} label="340-666.1" />);
        await waitFor(() => expect(fetchMock).toHaveBeenCalled());
        expect(fetchMock.mock.calls[0][0]).toMatch(/\/brain\/releases\/2\/drawing\/versions\?family=1$/);
    });

    it('groups the menu by release, original first, and marks the open one', async () => {
        render(<PdfViewerPane releaseId={2} label="340-666.1" />);
        await screen.findByTestId('canvas');
        openMenu();
        const menu = screen.getByRole('menu');
        expect(within(menu).getByText(/Release family drawings/i)).toBeInTheDocument();
        const text = menu.textContent;
        expect(text.indexOf('parent-v2.pdf')).toBeLessThan(text.indexOf('splice.pdf'));
        expect(within(menu).getByText(/Original/)).toBeInTheDocument();
        expect(within(menu).getByText(/Splice · this release/)).toBeInTheDocument();
    });

    it("opens the family's newest file and reads it through its OWN release", async () => {
        render(<PdfViewerPane releaseId={2} label="340-666.1" />);
        // Newest on the list is the original's v2 — owned by release 1, not the open row (2).
        expect(await screen.findByTestId('canvas')).toHaveTextContent('canvas 1/11');
        expect(screen.getByTestId('dock')).toHaveTextContent('dock 1');
        await waitFor(() => expect(jobsApi.getVersionComments).toHaveBeenCalledWith(1, 11));
        // Carmen review is prefetched per version, each through its owner.
        await waitFor(() => {
            expect(jobsApi.getBBReview).toHaveBeenCalledWith(1, 11);
            expect(jobsApi.getBBReview).toHaveBeenCalledWith(2, 20);
        });
    });

    it("comments on a sibling's file through the sibling's release", async () => {
        render(<PdfViewerPane releaseId={2} label="340-666.1" />);
        await screen.findByTestId('canvas');
        fireEvent.click(screen.getByText('draft'));
        fireEvent.click(screen.getByText('send'));
        await waitFor(() => expect(jobsApi.addVersionComment).toHaveBeenCalledWith(1, 11, 'hi'));
    });

    it('switching to the splice file swaps the canvas onto the splice', async () => {
        render(<PdfViewerPane releaseId={1} label="340-666" />);
        await screen.findByTestId('canvas');
        openMenu();
        fireEvent.click(within(screen.getByRole('menu')).getByText('splice.pdf'));
        expect(screen.getByTestId('canvas')).toHaveTextContent('canvas 2/20');
        expect(screen.getByTestId('dock')).toHaveTextContent('dock 2');
    });

    it('hands the owning release to the ↗ window', async () => {
        const onOpenVersion = vi.fn();
        render(<PdfViewerPane releaseId={2} label="340-666.1" onOpenVersion={onOpenVersion} />);
        await screen.findByTestId('canvas');
        fireEvent.click(screen.getByText('↗ window'));
        expect(onOpenVersion).toHaveBeenCalledWith(11, 'edit', 1);
    });

    it("uploads onto the open release's own chain, not the family's newest file", async () => {
        const { container } = render(<PdfViewerPane releaseId={2} label="340-666.1" />);
        await screen.findByTestId('canvas');
        const input = container.querySelector('input[type="file"]');
        const file = new File(['%PDF-1.4'], 'new.pdf', { type: 'application/pdf' });
        fireEvent.change(input, { target: { files: [file] } });

        await waitFor(() => expect(fetchMock.mock.calls.some(([, o]) => o?.method === 'POST')).toBe(true));
        const [url, opts] = fetchMock.mock.calls.find(([, o]) => o?.method === 'POST');
        expect(url).toMatch(/\/brain\/releases\/2\/drawing$/);
        // Release 2's newest is v20 — the original's v11 is newer overall but not its chain.
        expect(opts.body.get('source_version_id')).toBe('20');
    });

    it('stays a flat list for a release with no splices', async () => {
        fetchMock.mockImplementation(() => Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
                release_id: 5,
                versions: [v(50, 5, '400-100', 1, 'solo.pdf', false)],
                family: [{ release_id: 5, release_label: '400-100', is_splice: false, is_archived: false }],
            }),
        }));
        render(<PdfViewerPane releaseId={5} label="400-100" />);
        await screen.findByTestId('canvas');
        openMenu();
        const menu = screen.getByRole('menu');
        expect(within(menu).getByText('Drawings')).toBeInTheDocument();
        expect(within(menu).queryByText(/Original/)).toBeNull();
        expect(screen.getByText('+ Upload PDF')).toBeInTheDocument();
    });
});
