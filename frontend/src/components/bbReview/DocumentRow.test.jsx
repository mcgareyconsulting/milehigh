// Tests for the Re-pull action on a downloaded drawing row. The cached PDF is written
// once at pull time, so re-pull is the only way to pick up new approver markups — or to
// replace a copy a buggy build cached — and it must stay out of a running review's way.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import DocumentRow from './DocumentRow.jsx';
import { draftingWorkLoadApi } from '../../services/draftingWorkLoadApi';

vi.mock('../../services/draftingWorkLoadApi', () => ({
    draftingWorkLoadApi: {
        pullProcoreDocument: vi.fn(),
        runProcoreDocumentReview: vi.fn(),
        fetchProcoreDocumentReview: vi.fn(),
        saveProcoreDocumentReviewFeedback: vi.fn(),
    },
}));

const DOC = { attachment_id: 42, name: 'A-101.pdf', source: 'approver', downloaded: true, size_bytes: 2048 };

function renderRow(doc = DOC, props = {}) {
    const onUpdate = vi.fn();
    const onRefreshed = vi.fn();
    render(
        <DocumentRow
            submittalId="99"
            doc={doc}
            model="sonnet"
            onUpdate={onUpdate}
            onView={() => {}}
            onRefreshed={onRefreshed}
            {...props}
        />
    );
    return { onUpdate, onRefreshed };
}

beforeEach(() => {
    vi.clearAllMocks();
    draftingWorkLoadApi.pullProcoreDocument.mockResolvedValue({ size_bytes: 4096, name: 'A-101.pdf', source: 'approver' });
});

describe('DocumentRow re-pull', () => {
    it('offers Re-pull on a downloaded drawing', () => {
        renderRow();
        expect(screen.getByRole('button', { name: 'Re-pull' })).toBeInTheDocument();
    });

    it('does not offer Re-pull before the first pull', () => {
        renderRow({ ...DOC, downloaded: false });
        expect(screen.queryByRole('button', { name: 'Re-pull' })).not.toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Pull' })).toBeInTheDocument();
    });

    it('re-downloads, lifts the new size, and busts the viewer URL', async () => {
        const { onUpdate, onRefreshed } = renderRow();

        await userEvent.click(screen.getByRole('button', { name: 'Re-pull' }));

        await waitFor(() => expect(draftingWorkLoadApi.pullProcoreDocument).toHaveBeenCalledWith('99', 42));
        expect(onUpdate).toHaveBeenCalledWith(42, expect.objectContaining({ downloaded: true, size_bytes: 4096 }));
        // Without this the open viewer keeps rendering the copy it already loaded.
        await waitFor(() => expect(onRefreshed).toHaveBeenCalledWith(42));
    });

    it('surfaces a failed re-pull and leaves the row alone', async () => {
        draftingWorkLoadApi.pullProcoreDocument.mockRejectedValue(new Error('Procore render timed out'));
        const { onUpdate, onRefreshed } = renderRow();

        await userEvent.click(screen.getByRole('button', { name: 'Re-pull' }));

        expect(await screen.findByText('Procore render timed out')).toBeInTheDocument();
        expect(onUpdate).not.toHaveBeenCalled();
        expect(onRefreshed).not.toHaveBeenCalled();
    });

    it('is disabled while a review is reading the cached bytes', async () => {
        // A row that mounts mid-review polls server-side; the cache must not move under it.
        draftingWorkLoadApi.fetchProcoreDocumentReview.mockResolvedValue({ review: { status: 'pending' } });
        renderRow({ ...DOC, review: { status: 'pending', review_id: 7 } });

        expect(screen.getByRole('button', { name: 'Re-pull' })).toBeDisabled();
        expect(draftingWorkLoadApi.pullProcoreDocument).not.toHaveBeenCalled();
    });
});

describe('DocumentRow finding feedback notes', () => {
    const REVIEWED = {
        ...DOC,
        review: {
            review_id: 11,
            status: 'complete',
            model: 'sonnet',
            completed_at: new Date().toISOString(),
            tally: { high: 1, cleared: 0 },
            hold_recommended: false,
        },
    };

    const FINDING = {
        rule_id: 'R-01',
        issue: 'Missing weld callout',
        verdict: 'violation',
        severity: 'high',
        page: 2,
    };

    const openFindings = async (feedback = {}) => {
        draftingWorkLoadApi.fetchProcoreDocumentReview.mockResolvedValue({
            review: {
                review_id: 11,
                status: 'complete',
                findings: [FINDING],
                feedback,
            },
        });
        renderRow(REVIEWED);
        await userEvent.click(screen.getByRole('button', { name: /Findings/i }));
        // Placeholder changes once a decision is selected; match either state.
        return screen.findByRole('textbox');
    };

    it('shows a full notes area and commits decision + notes together on Save', async () => {
        draftingWorkLoadApi.saveProcoreDocumentReviewFeedback.mockResolvedValue({
            feedback: { finding_index: 0, decision: 'rejected', notes: 'false positive' },
        });

        const notes = await openFindings();
        expect(notes.tagName).toBe('TEXTAREA');
        expect(screen.getByRole('button', { name: /Accept/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Reject/i })).toBeInTheDocument();

        // Accept/Reject alone must not hit the network — that was the clunky double-save.
        await userEvent.click(screen.getByRole('button', { name: /Reject/i }));
        expect(draftingWorkLoadApi.saveProcoreDocumentReviewFeedback).not.toHaveBeenCalled();

        await userEvent.type(notes, 'false positive');
        await userEvent.click(screen.getByRole('button', { name: /Save feedback/i }));

        await waitFor(() =>
            expect(draftingWorkLoadApi.saveProcoreDocumentReviewFeedback).toHaveBeenCalledTimes(1)
        );
        expect(draftingWorkLoadApi.saveProcoreDocumentReviewFeedback).toHaveBeenCalledWith(
            '99',
            42,
            11,
            expect.objectContaining({
                finding_index: 0,
                decision: 'rejected',
                notes: 'false positive',
                rule_id: 'R-01',
            })
        );
        expect(await screen.findByText('Saved')).toBeInTheDocument();
    });

    it('seeds prior notes and only saves after an explicit Save', async () => {
        draftingWorkLoadApi.saveProcoreDocumentReviewFeedback.mockResolvedValue({
            feedback: { finding_index: 0, decision: 'accepted', notes: 'looks good, confirmed' },
        });

        const notes = await openFindings({ 0: { decision: 'accepted', notes: 'looks good' } });
        expect(notes).toHaveValue('looks good');
        expect(screen.getByText('Saved')).toBeInTheDocument();

        await userEvent.clear(notes);
        await userEvent.type(notes, 'looks good, confirmed');
        expect(screen.getByText('Unsaved')).toBeInTheDocument();
        expect(draftingWorkLoadApi.saveProcoreDocumentReviewFeedback).not.toHaveBeenCalled();

        await userEvent.click(screen.getByRole('button', { name: /Save feedback/i }));

        await waitFor(() =>
            expect(draftingWorkLoadApi.saveProcoreDocumentReviewFeedback).toHaveBeenCalledWith(
                '99',
                42,
                11,
                expect.objectContaining({
                    finding_index: 0,
                    decision: 'accepted',
                    notes: 'looks good, confirmed',
                })
            )
        );
    });

    it('can save a decision with an empty note in one shot', async () => {
        draftingWorkLoadApi.saveProcoreDocumentReviewFeedback.mockResolvedValue({
            feedback: { finding_index: 0, decision: 'accepted', notes: null },
        });

        await openFindings();
        await userEvent.click(screen.getByRole('button', { name: /Accept/i }));
        await userEvent.click(screen.getByRole('button', { name: /Save feedback/i }));

        await waitFor(() =>
            expect(draftingWorkLoadApi.saveProcoreDocumentReviewFeedback).toHaveBeenCalledWith(
                '99',
                42,
                11,
                expect.objectContaining({
                    finding_index: 0,
                    decision: 'accepted',
                    notes: '',
                })
            )
        );
    });
});
