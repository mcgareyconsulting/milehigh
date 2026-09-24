import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import SubStageGateSheet from './SubStageGateSheet';

const photo = (over = {}) => ({
    id: 4,
    stage: 'Paint QC',
    original_filename: 'shop.jpg',
    note: '',
    uploaded_by_name: 'Bill Shop',
    ...over,
});

function renderSheet(photos, extras = {}) {
    const api = {
        getAttachments: vi.fn(async () => ({ photos, drawings: [] })),
        photoFileUrl: (releaseId, photoId) => `http://photos/${releaseId}/${photoId}`,
        uploadPhoto: vi.fn(async () => ({ id: 9, stage: 'Ship Complete' })),
        tagPhoto: vi.fn(async (_id, photoId, stage) => ({ id: photoId, stage })),
        ...extras.api,
    };
    const onSatisfied = vi.fn(async () => {});
    const onClose = vi.fn();
    render(
        <SubStageGateSheet
            gateStage="Ship Complete"
            requestedStage="Install Start"
            releaseId={7}
            api={api}
            onSatisfied={onSatisfied}
            onClose={onClose}
        />,
    );
    return { api, onSatisfied, onClose };
}

describe('SubStageGateSheet', () => {
    it('shows photos already on the release and does not treat another stage as evidence', async () => {
        renderSheet([photo()]);
        expect(await screen.findByText('shop.jpg')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'View shop.jpg' }).querySelector('img'))
            .toHaveAttribute('src', 'http://photos/7/4');
        expect(screen.getByText(/Tagged Paint QC/)).toBeInTheDocument();
        expect(screen.getByRole('checkbox', { name: 'Use for Ship Complete' })).not.toBeChecked();
        expect(screen.queryByRole('button', { name: 'Move to Install Start' })).toBeNull();
    });

    it('retags a selected photo and then moves the stage', async () => {
        const { api, onSatisfied } = renderSheet([photo()]);
        fireEvent.click(await screen.findByRole('checkbox', { name: 'Use for Ship Complete' }));
        fireEvent.click(screen.getByRole('button', { name: 'Move to Install Start' }));
        await waitFor(() => expect(onSatisfied).toHaveBeenCalledWith({}));
        expect(api.tagPhoto).toHaveBeenCalledWith(7, 4, 'Ship Complete');
    });

    it('opens a photo full size without using it as evidence', async () => {
        renderSheet([photo()]);
        fireEvent.click(await screen.findByRole('button', { name: 'View shop.jpg' }));
        expect(screen.getByRole('dialog', { name: 'Photo' })).toBeInTheDocument();
        expect(screen.getByRole('img', { name: 'shop.jpg' })).toHaveAttribute('src', 'http://photos/7/4');
    });

    it('hides the no-photo exit once a photo is included', async () => {
        renderSheet([photo()]);
        expect(await screen.findByRole('button', { name: 'No photo available…' })).toBeInTheDocument();
        fireEvent.click(screen.getByRole('checkbox', { name: 'Use for Ship Complete' }));
        expect(screen.queryByRole('button', { name: 'No photo available…' })).toBeNull();
    });
});
