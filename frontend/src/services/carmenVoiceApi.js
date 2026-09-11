/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP calls for Carmen's voice-to-voice turn (xAI speech-to-text -> Carmen agent
 *          -> xAI text-to-speech). Also converts the base64 audio envelope the server
 *          returns into a playable object URL.
 * exports:
 *   getVoiceConfig: Is voice live on this server, and in which voice?
 *   sendVoiceTurn: POST a mic recording; returns the same turn shape as sendMessage plus
 *                  { transcript, audio, voice_timings }.
 *   speakText: POST answer text; returns an audio envelope so a written reply can be replayed.
 *   audioUrlFromEnvelope: base64 envelope -> blob object URL (caller revokes it).
 *   startLiveSession: mint an xAI client secret + the session config for live mode.
 *   runLiveTool: execute one of Carmen's read-only tools for the live session.
 *   saveLiveTurn: file a spoken exchange into the chat history.
 *   applyLiveChanges: execute a confirmed change proposal (admin; the only write here).
 *   undoLiveEvent: reverse one applied change by its ReleaseEvents id.
 * imports_from: [axios, ../utils/api]
 * imported_by: [components/BBChatWidget.jsx, hooks/useCarmenLive.js]
 * invariants:
 *   - withCredentials sends the session cookie; access is enforced server-side by is_carmen_chat.
 *   - The voice turn is read-only: it runs the same agent the typed chat runs.
 *   - The live client secret is short-lived and scoped to one session; the real xAI key
 *     never reaches the browser.
 *   - Object URLs created here must be revoked by the caller when the clip is replaced.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;
const BASE = `${API_BASE_URL}/brain/carmen-chat/voice`;

export async function getVoiceConfig() {
    const { data } = await axios.get(`${BASE}/config`);
    return data; // { enabled, configured, voice_id, language, max_upload_bytes }
}

/**
 * Send one spoken turn.
 * @param {Blob} blob recording from MediaRecorder
 * @param {number|null} conversationId thread to continue, or null to start one
 * @param {string} filename extension-bearing name so the server can label the upload
 */
export async function sendVoiceTurn(blob, conversationId, filename = 'clip.webm') {
    const form = new FormData();
    form.append('audio', blob, filename);
    if (conversationId) form.append('conversation_id', String(conversationId));
    const { data } = await axios.post(BASE, form);
    return data; // { conversation_id, transcript, user_message, assistant_message, audio, ... }
}

export async function speakText(text, voiceId) {
    const { data } = await axios.post(`${BASE}/speak`, {
        text,
        voice_id: voiceId || undefined,
    });
    return data; // { data_base64, mime, duration_seconds, voice_id, chars, truncated }
}

/** Turn the server's base64 audio envelope into a URL an <audio> element can play. */
export function audioUrlFromEnvelope(envelope) {
    if (!envelope?.data_base64) return null;
    const bin = atob(envelope.data_base64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
    return URL.createObjectURL(new Blob([bytes], { type: envelope.mime || 'audio/mpeg' }));
}

// --- Live mode ------------------------------------------------------------------------

/** Mint a client secret plus the server-authored session config (prompt + tool schemas). */
export async function startLiveSession() {
    const { data } = await axios.post(`${BASE}/live/token`);
    return data; // { token, url, model, session, ttl_seconds, max_session_seconds }
}

/** Run one read-only tool on behalf of the live session. Never throws — the model gets a result either way. */
export async function runLiveTool(name, args) {
    try {
        const { data } = await axios.post(`${BASE}/live/tool`, { name, arguments: args || {} });
        return data; // { result, artifact, proposal? }
    } catch (err) {
        return { result: { error: err?.response?.data?.error || 'that lookup failed' }, artifact: null };
    }
}

/** Persist one spoken exchange so the live conversation survives the tab. */
export async function saveLiveTurn(userText, assistantText, conversationId) {
    const { data } = await axios.post(`${BASE}/live/turn`, {
        user_text: userText || '',
        assistant_text: assistantText || '',
        conversation_id: conversationId || undefined,
    });
    return data; // { conversation_id }
}

/**
 * Apply a change proposal the user confirmed. The plan and token must go back EXACTLY as
 * they were issued — the server verifies a signature over them and will reject an edit.
 */
export async function applyLiveChanges(proposal) {
    const { data } = await axios.post(`${BASE}/live/apply`, {
        plan: proposal.plan,
        token: proposal.token,
        issued_at: proposal.issued_at,
    });
    return data; // { applied, failed, results, event_ids, job, release }
}

/** Reverse one applied change. Reuses the Job Log's existing undo endpoint. */
export async function undoLiveEvent(eventId) {
    const { data } = await axios.post(`${API_BASE_URL}/brain/events/${eventId}/undo`);
    return data;
}
