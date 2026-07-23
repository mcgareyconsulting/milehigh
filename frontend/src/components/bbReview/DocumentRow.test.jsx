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
