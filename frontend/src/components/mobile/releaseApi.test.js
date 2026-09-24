import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), defaults: {} } }));
vi.mock('../../services/jobsApi', () => ({
    jobsApi: {
        getRelease: vi.fn(), getReleaseChecklist: vi.fn(), updateStage: vi.fn(), getNotesHistory: vi.fn(),
        updateNotes: vi.fn(), getReleasePhotos: vi.fn(), getReleaseDrawings: vi.fn(),
    },
}));

import axios from 'axios';
import { jobsApi } from '../../services/jobsApi';
import { staffReleaseApi } from './releaseApi';

const rel = { 'Job #': 560, 'Release #': '923' };

describe('staffReleaseApi', () => {
    beforeEach(() => vi.clearAllMocks());

    it('offers the full stage progression and 404s a missing release', async () => {
        jobsApi.getRelease.mockResolvedValueOnce({ id: 1, ...rel });
        const r = await staffReleaseApi.getRelease(1);
        expect(r.stage_options[0]).toBe('Released');
        expect(r.stage_options).toContain('Install Complete');
        jobsApi.getRelease.mockResolvedValueOnce(null);
        await expect(staffReleaseApi.getRelease(2)).rejects.toMatchObject({ response: { status: 404 } });
    });

    it('routes stage and notes through job + release, and tags sub actors in activity', async () => {
        axios.patch.mockResolvedValueOnce({ data: { status: 'success' } });
        await staffReleaseApi.setStage(1, rel, 'Install Start');
        expect(axios.patch).toHaveBeenCalledWith(expect.stringContaining('/brain/update-stage/560/923'), { stage: 'Install Start' });
        axios.patch.mockResolvedValueOnce({ data: { status: 'success' } });
        await staffReleaseApi.setStage(1, rel, 'Install Start', { gateExceptionNote: 'no truck photo' });
        expect(axios.patch).toHaveBeenLastCalledWith(expect.anything(), { stage: 'Install Start', gate_exception_note: 'no truck photo' });
        await staffReleaseApi.addNote(1, rel, 'hi');
        expect(jobsApi.updateNotes).toHaveBeenCalledWith(560, '923', 'hi');
        jobsApi.getNotesHistory.mockResolvedValueOnce({ events: [
            { id: 1, action: 'update_notes', external_user_id: 'sub:4', user_name: 'Sam Sub (Acme)' },
            { id: 2, action: 'update_stage', user_name: 'Bill' },
            { id: 3, action: 'update_stage', user_name: null },
        ] });
        const rows = await staffReleaseApi.getActivity(1, rel);
        expect(rows.map((e) => e.actor_kind)).toEqual(['sub', 'staff', 'system']);
    });

    it('maps family drawings with the current version flagged and photos to the shared shape', async () => {
        axios.get.mockResolvedValueOnce({ data: { versions: [
            { id: 10, release_id: 1, release_label: '560-923', version_number: 2, original_filename: 'b.pdf', uploaded_by: { name: 'Bill' } },
            { id: 9, release_id: 1, release_label: '560-923', version_number: 1, original_filename: 'a.pdf', uploaded_by: { name: 'Bill' } },
            { id: 20, release_id: 2, release_label: '560-923.1', version_number: 1, uploaded_by: { name: 'Sam Sub' } },
        ] } });
        jobsApi.getReleasePhotos.mockResolvedValueOnce([{ id: 5, original_filename: 'p.jpg', uploaded_by: { name: 'Sam' }, stage: null }]);
        const out = await staffReleaseApi.getAttachments(1);
        expect(axios.get).toHaveBeenCalledWith(expect.stringContaining('/brain/releases/1/drawing/versions'), { params: { family: 1 } });
        expect(out.drawings.map((d) => [d.id, d.is_current, d.uploaded_by_name])).toEqual([[10, true, 'Bill'], [9, false, 'Bill'], [20, true, 'Sam Sub']]);
        expect(out.photos[0]).toMatchObject({ id: 5, uploaded_by_name: 'Sam' });
    });

    it('tags a gate photo with the stage', async () => {
        axios.post.mockResolvedValueOnce({ data: { id: 5 } });
        await staffReleaseApi.uploadPhoto(1, new File([new Uint8Array([1])], 'h.jpg', { type: 'image/jpeg' }), { stage: 'Ship Complete' });
        expect(axios.post.mock.calls[0][1].get('stage')).toBe('Ship Complete');
    });

    it('derives a later PDF upload from the release\'s own latest version', async () => {
        jobsApi.getReleaseDrawings.mockResolvedValueOnce([{ id: 9, version_number: 1 }, { id: 10, version_number: 2 }]);
        axios.post.mockResolvedValueOnce({ data: { id: 11 } });
        await staffReleaseApi.uploadFile(1, new File([new Uint8Array([1])], 'c.pdf', { type: 'application/pdf' }));
        const form = axios.post.mock.calls[0][1];
        expect(axios.post.mock.calls[0][0]).toContain('/brain/releases/1/drawing');
        expect(form.get('source_version_id')).toBe('10');
    });
});
