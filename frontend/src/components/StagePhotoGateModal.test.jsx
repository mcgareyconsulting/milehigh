/**
 * The department photo gate dialog (T13): what unlocks Confirm, the "no photo available" exit,
 * and the multi-photo upload strip — cap, one-at-a-time queue, real progress, retry.
 *
 * Uploads go through XMLHttpRequest for byte progress, so a small fake XHR stands in and the
 * tests drive progress / load / error by hand. Everything else (the photo list, notes) is fetch.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, within, waitFor, fireEvent } from '@testing-library/react';

vi.mock('../utils/imageCompress', () => ({ compressImage: (file) => Promise.resolve(file) }));
vi.mock('../utils/api', () => ({ API_BASE_URL: 'http://api.test' }));
vi.mock('./pdfViewer/format', () => ({ fmtDate: () => 'Sep 23', fmtSize: () => '1 KB' }));

import { StagePhotoGateModal } from './StagePhotoGateModal';

// ---- fakes -------------------------------------------------------------------------------

const photosRef = { current: [] };

const photo = (over = {}) => ({
    id: 1,
    stage: 'Welded QC',
    original_filename: 'weld.jpg',
    uploaded_at: '2026-09-23T10:00:00Z',
    uploaded_by: { name: 'Louie' },
    file_size_bytes: 1000,
    note: '',
    ...over,
});

const xhrs = [];
class FakeXHR {
    constructor() {
        this.upload = {};
        this.status = 0;
        this.responseText = '';
        this.withCredentials = false;
        this.sent = false;
        xhrs.push(this);
    }
    open(method, url) { this.method = method; this.url = url; }
    send(body) { this.body = body; this.sent = true; }
    // Test-side controls.
    progress(loaded, total) { this.upload.onprogress?.({ lengthComputable: true, loaded, total }); }
    respond(status = 201) { this.status = status; this.onload?.(); }
    fail() { this.onerror?.(); }
}

const file = (name) => new File(['x'], name, { type: 'image/jpeg' });
const pickerInput = () => document.querySelector('input[type="file"]:not([capture])');
const pick = async (files) => {
    await act(async () => { fireEvent.change(pickerInput(), { target: { files } }); });
};
const tiles = () => screen.queryAllByTitle(/^p\d+\.jpg/);
const confirmBtn = () => screen.getByRole('button', { name: /^Confirm / });
const nextSend = async (n) => waitFor(() => expect(xhrs.filter((x) => x.sent).length).toBe(n));

const renderGate = (props = {}) => {
    const onConfirmStage = vi.fn();
    const onClose = vi.fn();
    render(
        <StagePhotoGateModal
            isOpen
            releaseId={7}
            title="560-923"
            gateStage="Welded QC"
            requestedStage="Welded QC"
            onConfirmStage={onConfirmStage}
            onClose={onClose}
            {...props}
        />,
    );
    return { onConfirmStage, onClose };
};

beforeEach(() => {
    photosRef.current = [];
    xhrs.length = 0;
    globalThis.XMLHttpRequest = FakeXHR;
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:preview');
    globalThis.URL.revokeObjectURL = vi.fn();
    globalThis.fetch = vi.fn((url, opts = {}) => {
        const method = (opts.method || 'GET').toUpperCase();
        if (method === 'GET') {
            return Promise.resolve({ ok: true, json: () => Promise.resolve({ photos: photosRef.current }) });
        }
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });
});

afterEach(() => {
    vi.restoreAllMocks();
});

// ---- what unlocks Confirm ----------------------------------------------------------------

describe('unlocking Confirm', () => {
    it('stays disabled with no tagged photo', async () => {
        renderGate();
        await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
        expect(confirmBtn()).toBeDisabled();
        expect(screen.getByText(/A Welded QC photo is required to move to Welded QC/)).toBeInTheDocument();
    });

    it('unlocks once a photo tagged with the gate stage exists', async () => {
        photosRef.current = [photo()];
        const { onConfirmStage } = renderGate();
        await waitFor(() => expect(confirmBtn()).toBeEnabled());
        expect(screen.getByText(/✓ Welded QC photo attached/)).toBeInTheDocument();

        fireEvent.click(confirmBtn());
        expect(onConfirmStage).toHaveBeenCalledWith(null);
    });

    it('is not satisfied by a photo tagged with another stage', async () => {
        photosRef.current = [photo({ stage: 'Paint QC' })];
        renderGate();
        await screen.findByText('Paint QC');   // the photo rendered with its own tag
        expect(confirmBtn()).toBeDisabled();
    });
});

describe('the header', () => {
    it('names the stage the user picked', async () => {
        renderGate({ gateStage: 'Welded QC', requestedStage: 'Welded QC' });
        const line = screen.getByText(/Required before moving to/);
        expect(line).toHaveTextContent('Required before moving to Welded QC');
        expect(line).not.toHaveTextContent('handoff');
    });

    it('names the handoff when the pick skips the entry stage', async () => {
        renderGate({ gateStage: 'Ship Complete', requestedStage: 'Complete' });
        const line = screen.getByText(/Required before moving to/);
        expect(line).toHaveTextContent('Required before moving to Complete');
        expect(line).toHaveTextContent('the Ship Complete handoff');
        expect(confirmBtn()).toHaveTextContent('Confirm Complete');
    });
});

// ---- the "no photo available" exit -------------------------------------------------------

describe('no photo available', () => {
    it('needs a real reason, then confirms with it trimmed', async () => {
        const { onConfirmStage } = renderGate();
        await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());

        expect(screen.queryByPlaceholderText(/Why is there no Welded QC photo/)).toBeNull();
        fireEvent.click(screen.getByLabelText('No photo available'));
        const box = screen.getByPlaceholderText('Why is there no Welded QC photo? (required)');
        expect(confirmBtn()).toBeDisabled();

        fireEvent.change(box, { target: { value: '   ' } });
        expect(confirmBtn()).toBeDisabled();

        fireEvent.change(box, { target: { value: '  ship plates, nothing to shoot  ' } });
        expect(confirmBtn()).toBeEnabled();
        expect(screen.getByText(/Moving without a photo/)).toBeInTheDocument();

        fireEvent.click(confirmBtn());
        expect(onConfirmStage).toHaveBeenCalledWith('ship plates, nothing to shoot');
    });

    it('is not offered once a tagged photo is attached', async () => {
        photosRef.current = [photo()];
        renderGate();
        await waitFor(() => expect(confirmBtn()).toBeEnabled());
        expect(screen.queryByLabelText('No photo available')).toBeNull();
    });
});

// ---- the upload strip --------------------------------------------------------------------

describe('picking photos', () => {
    it('takes ten at a time and says so when given more', async () => {
        renderGate();
        await pick(Array.from({ length: 12 }, (_, i) => file(`p${i + 1}.jpg`)));

        await waitFor(() => expect(tiles()).toHaveLength(10));
        const notice = screen.getByText(/10 at a time/);
        expect(notice).toHaveTextContent('the first 10 were added');
        expect(notice).toHaveTextContent('other 2');
    });

    it('takes a small pick without comment', async () => {
        renderGate();
        await pick([file('p1.jpg'), file('p2.jpg'), file('p3.jpg')]);

        await waitFor(() => expect(tiles()).toHaveLength(3));
        expect(screen.queryByText(/at a time/)).toBeNull();
    });

    it('sends each file tagged with the gate stage', async () => {
        renderGate({ gateStage: 'Paint QC', requestedStage: 'Paint QC' });
        await pick([file('p1.jpg')]);
        await nextSend(1);

        const xhr = xhrs[0];
        expect(xhr.method).toBe('POST');
        expect(xhr.url).toBe('http://api.test/brain/releases/7/photos');
        expect(xhr.withCredentials).toBe(true);
        expect(xhr.body).toBeInstanceOf(FormData);
        expect(xhr.body.get('stage')).toBe('Paint QC');
        expect(xhr.body.get('file')).toBeInstanceOf(File);
        expect(xhr.body.get('file').name).toBe('p1.jpg');
    });
});

describe('progress', () => {
    it('uploads one at a time with real byte progress and holds Confirm meanwhile', async () => {
        photosRef.current = [photo()];   // already satisfied — the upload is what holds Confirm
        renderGate();
        await waitFor(() => expect(confirmBtn()).toBeEnabled());

        await pick([file('p1.jpg'), file('p2.jpg')]);
        await nextSend(1);
        expect(screen.getByText('Uploading 1 of 2…')).toBeInTheDocument();
        expect(confirmBtn()).toBeDisabled();
        expect(confirmBtn()).toHaveAttribute('title', 'Wait for the uploads to finish');

        const [first] = tiles();
        expect(within(tiles()[1]).getByText('queued')).toBeInTheDocument();
        act(() => { xhrs[0].progress(50, 100); });
        expect(first.querySelector('.bg-accent-500').style.width).toBe('50%');

        act(() => { xhrs[0].respond(201); });
        await waitFor(() => expect(within(tiles()[0]).getByText('✓')).toBeInTheDocument());
        await nextSend(2);
        expect(screen.getByText('Uploading 2 of 2…')).toBeInTheDocument();
        expect(confirmBtn()).toBeDisabled();

        act(() => { xhrs[1].respond(201); });
        await waitFor(() => expect(screen.getByText('2 uploaded')).toBeInTheDocument());
        expect(confirmBtn()).toBeEnabled();
    });

    it('labels the camera button by what has landed', async () => {
        renderGate();
        await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
        expect(screen.getByRole('button', { name: /Take photo/ })).toBeInTheDocument();

        photosRef.current = [photo()];
        await pick([file('p1.jpg')]);
        await waitFor(() => expect(screen.getByRole('button', { name: /Take another/ })).toBeInTheDocument());
    });
});

describe('failure', () => {
    it('marks the failed photo Retry, keeps going, and re-sends on Retry', async () => {
        renderGate();
        await pick([file('p1.jpg'), file('p2.jpg')]);
        await nextSend(1);

        act(() => { xhrs[0].fail(); });
        await waitFor(() => expect(within(tiles()[0]).getByRole('button', { name: 'Retry' })).toBeInTheDocument());
        await nextSend(2);   // the second file was not stopped by the first

        act(() => { xhrs[1].respond(201); });
        await waitFor(() => expect(screen.getByText("1 of 2 didn't upload")).toBeInTheDocument());
        expect(screen.getByRole('button', { name: 'Retry failed' })).toBeInTheDocument();
        expect(tiles()[0]).toHaveAttribute('title', expect.stringContaining('network error'));

        fireEvent.click(within(tiles()[0]).getByRole('button', { name: 'Retry' }));
        await nextSend(3);
        expect(xhrs[2].body.get('file').name).toBe('p1.jpg');
        expect(screen.getByText('Uploading 2 of 2…')).toBeInTheDocument();

        act(() => { xhrs[2].respond(201); });
        await waitFor(() => expect(screen.getByText('2 uploaded')).toBeInTheDocument());
    });
});
