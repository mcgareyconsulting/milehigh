/**
 * @milehigh-header
 * schema_version: 1
 * purpose: The data adapter behind the phone release page (components/mobile/MobileReleasePage).
 *          One contract, two implementations: `subReleaseApi` reads the sub-scoped routes for a
 *          subcontractor session; `staffReleaseApi` reads the ordinary staff routes for an employee,
 *          so the SAME page renders for both and the client can test one surface on any login.
 * exports:
 *   subReleaseApi, staffReleaseApi — each:
 *     getRelease(id) -> { release, stage_options }
 *     listTodosForRelease(id) -> [{ id, title, due_date, status, release_id }]
 *     setStage(id, rel, stage), getActivity(id, rel) -> rows, addNote(id, rel, text)
 *     getAttachments(id) -> { drawings, photos }, uploadPhoto(id, file), uploadFile(id, file)
 *     drawingFileUrl(releaseId, versionId), photoFileUrl(releaseId, photoId)
 * imports_from: [axios, ../../utils/api, ../../services/subPortalApi, ../../services/jobsApi, ../../constants/stages]
 * imported_by: [pages/SubcontractorRelease.jsx, pages/mobile/StaffMobileRelease.jsx]
 * invariants:
 *   - Scoping stays server-side in both: the sub adapter never sees a staff route, and the staff
 *     adapter is only reachable behind a staff session.
 *   - Staff stage options are the full ordered progression; sub options come from the server.
 */
import axios from 'axios';
import { API_BASE_URL } from '../../utils/api';
import { jobsApi } from '../../services/jobsApi';
import { STAGE_OPTIONS } from '../../constants/stages';
import {
    getSubRelease, listSubTodos, setSubStage, getSubActivity, addSubNote, getSubAttachments,
    uploadSubPhoto, uploadSubFile, subDrawingFileUrl, subPhotoFileUrl,
} from '../../services/subPortalApi';

axios.defaults.withCredentials = true;

export const subReleaseApi = {
    getRelease: (id) => getSubRelease(id),
    listTodosForRelease: (id) => listSubTodos('all').then((t) => t.filter((x) => x.release_id === id)),
    setStage: (id, _rel, stage) => setSubStage(id, stage),
    getActivity: (id) => getSubActivity(id),
    addNote: (id, _rel, text) => addSubNote(id, text),
    getAttachments: (id) => getSubAttachments(id),
    uploadPhoto: (id, file) => uploadSubPhoto(id, file),
    uploadFile: (id, file) => uploadSubFile(id, file),
    drawingFileUrl: subDrawingFileUrl,
    photoFileUrl: subPhotoFileUrl,
};

const BRAIN = `${API_BASE_URL}/brain`;
const jobOf = (rel) => rel['Job #'];
const relOf = (rel) => rel['Release #'];

export const staffReleaseApi = {
    async getRelease(id) {
        const release = await jobsApi.getRelease(id);
        if (!release) { const e = new Error('Release not found'); e.response = { status: 404 }; throw e; }
        return { release, stage_options: STAGE_OPTIONS.map((s) => s.value) };
    },
    listTodosForRelease: (id) => jobsApi.getReleaseChecklist(id).then((d) => (d.todos || []).map((t) => ({
        id: t.id, title: t.title, due_date: t.due_date, status: t.status, release_id: t.release_id,
    }))),
    setStage: (_id, rel, stage) => jobsApi.updateStage(jobOf(rel), relOf(rel), stage),
    getActivity: (_id, rel) => jobsApi.getNotesHistory(jobOf(rel), relOf(rel), 200).then((d) => (d.events || []).map((e) => ({
        ...e,
        actor_kind: String(e.external_user_id || '').startsWith('sub:') ? 'sub' : (e.user_name ? 'staff' : 'system'),
    }))),
    addNote: (_id, rel, text) => jobsApi.updateNotes(jobOf(rel), relOf(rel), text),
    async getAttachments(id) {
        const [{ data: dv }, photos] = await Promise.all([
            axios.get(`${BRAIN}/releases/${id}/drawing/versions`, { params: { family: 1 } }),
            jobsApi.getReleasePhotos(id),
        ]);
        const versions = dv.versions || [];
        const latest = {};
        versions.forEach((v) => { latest[v.release_id] = Math.max(latest[v.release_id] || 0, v.version_number); });
        return {
            drawings: versions.map((v) => ({
                id: v.id, release_id: v.release_id, release_label: v.release_label, version_number: v.version_number,
                is_current: v.version_number === latest[v.release_id], original_filename: v.original_filename,
                file_size_bytes: v.file_size_bytes, uploaded_at: v.uploaded_at, uploaded_by_name: v.uploaded_by?.name, note: v.note,
            })),
            photos: photos.map((p) => ({
                id: p.id, original_filename: p.original_filename, mime_type: p.mime_type, file_size_bytes: p.file_size_bytes,
                note: p.note, stage: p.stage, uploaded_at: p.uploaded_at, uploaded_by_name: p.uploaded_by?.name,
            })),
        };
    },
    async uploadPhoto(id, file) {
        const form = new FormData();
        form.append('file', file, file.name || 'photo.jpg');
        const { data } = await axios.post(`${BRAIN}/releases/${id}/photos`, form, { headers: { 'Content-Type': 'multipart/form-data' } });
        return data;
    },
    async uploadFile(id, file) {
        // A later upload needs the version it derives from — the release's own latest.
        const own = await jobsApi.getReleaseDrawings(id);
        const latest = own.reduce((a, v) => (!a || v.version_number > a.version_number ? v : a), null);
        const form = new FormData();
        form.append('file', file, file.name || 'file.pdf');
        if (latest) form.append('source_version_id', String(latest.id));
        const { data } = await axios.post(`${BRAIN}/releases/${id}/drawing`, form, { headers: { 'Content-Type': 'multipart/form-data' } });
        return data;
    },
    drawingFileUrl: (releaseId, versionId) => `${BRAIN}/releases/${releaseId}/drawing/versions/${versionId}/file`,
    photoFileUrl: (releaseId, photoId) => `${BRAIN}/releases/${releaseId}/photos/${photoId}/file`,
};
