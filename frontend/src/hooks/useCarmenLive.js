/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Drives a live (realtime) Carmen conversation. Holds the WebSocket to xAI,
 *          streams mic PCM up, plays her PCM back, bridges her tool calls to our server,
 *          and files each completed exchange into chat history.
 * exports:
 *   useCarmenLive: default. ({ conversationId, onConversationId, onUserText, onAssistantText,
 *                  onArtifact, onProposal }) ->
 *                  { supported, status, error, speaking, userSpeaking, partial, elapsed,
 *                    start, stop, notifyApplied }.
 * imports_from: [react, ../services/carmenVoiceApi, ../utils/livePcm]
 * imported_by: [components/BBChatWidget.jsx]
 * invariants:
 *   - The browser holds the socket, not Flask — the server only brokers (see live.py).
 *   - The mic and both AudioContexts are released on stop(), on error, and on unmount.
 *   - Barge-in clears queued playback the instant the server reports user speech.
 *   - Tool results always go back to the model, even on failure, or the turn hangs.
 *   - A change proposal is surfaced to the UI but NEVER applied here — confirmation is a
 *     human action on the card, never something the model can trigger for itself.
 *   - On a proposal turn she still SPEAKS, but her words are not written to the chat: the
 *     card is the record, and a transcript of "confirm when you're ready" beside it is
 *     just the same thing twice.
 *   - notifyApplied only TELLS her what a human already did. It carries no authority to
 *     write and is called after the fact, so it can't become a back door to applying.
 *   - Messages render as they happen, not at end of turn: the user's transcript when it
 *     finalises, then her written answer the moment write_to_chat arrives — so there is
 *     something to read before she starts speaking.
 *   - VAD can split ONE spoken sentence into several transcription items. Each item's
 *     transcript is CUMULATIVE and gets re-sent as it firms up, so items are tracked by
 *     item_id and REPLACED, never appended — appending turns one sentence into
 *     "Move one Move 17045 Move 170453 to stage. Move 170453 to stage install start…".
 *     The joined result is re-emitted under one turnId so the widget updates one bubble.
 *   - A tool call ENDS its response, so one spoken turn spans several `response.done`
 *     events. The follow-up flag is set SYNCHRONOUSLY on the tool-call event (never after
 *     an await) or a fast `response.done` flushes the turn mid-lookup.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { runLiveTool, saveLiveTurn, startLiveSession } from '../services/carmenVoiceApi';
import { MicCapture, PcmPlayer } from '../utils/livePcm';

// The realtime event vocabulary is young and still shifting; accept the aliases we have
// seen rather than hard-failing on a rename. Unknown events are logged, never fatal.
const AUDIO_DELTA = new Set(['response.output_audio.delta', 'response.audio.delta']);
const TEXT_DELTA = new Set([
    'response.output_audio_transcript.delta',
    'response.audio_transcript.delta',
    'response.output_text.delta',
]);
const TEXT_DONE = new Set([
    'response.output_audio_transcript.done',
    'response.audio_transcript.done',
]);
// She speaks the summary and writes the detail; this is the tool that carries the detail.
// Handled here rather than on the server — no round trip, no added latency, no cost beyond
// the text she was already generating.
const WRITE_TO_CHAT = 'write_to_chat';

const USER_TRANSCRIPT = new Set([
    'conversation.item.input_audio_transcription.updated',
    'conversation.item.input_audio_transcription.completed',
    'conversation.item.input_audio_transcription.delta',
]);

export default function useCarmenLive({
    conversationId,
    onConversationId,
    onUserText,
    onAssistantText,
    onArtifact,
    onProposal,
    debug = false,
} = {}) {
    const [status, setStatus] = useState('idle'); // idle | connecting | live | error
    const [error, setError] = useState('');
    const [speaking, setSpeaking] = useState(false);
    const [userSpeaking, setUserSpeaking] = useState(false);
    const [partial, setPartial] = useState({ user: '', assistant: '' });
    const [elapsed, setElapsed] = useState(0);

    const wsRef = useRef(null);
    const micRef = useRef(null);
    const playerRef = useRef(null);
    const tickRef = useRef(null);
    const limitRef = useRef(null);
    // `postedUser` / `postedWritten` stop a turn's messages being rendered twice, since
    // they now go up as they happen rather than all at once when the turn closes.
    const turnRef = useRef({ user: '', assistant: '', written: '', postedUser: false, postedWritten: false, proposed: false, items: [] });
    const convoRef = useRef(conversationId || null);
    const stoppingRef = useRef(false);
    // True between dispatching a data tool call and the response it produces: the turn is
    // still in flight, so the `response.done` that closed the tool call must not flush it.
    const awaitingFollowUpRef = useRef(false);
    // Her spoken "done" after a confirmed change is worth hearing and not worth reading —
    // the card right above it already shows the ticks.
    const silentTurnRef = useRef(false);
    const turnIdRef = useRef(0);
    const cbRef = useRef({ onUserText, onAssistantText, onArtifact, onConversationId, onProposal });
    cbRef.current = { onUserText, onAssistantText, onArtifact, onConversationId, onProposal };
    convoRef.current = conversationId ?? convoRef.current;

    const supported = typeof window !== 'undefined'
        && typeof window.WebSocket !== 'undefined'
        && typeof window.AudioWorkletNode !== 'undefined'
        && !!navigator?.mediaDevices?.getUserMedia;

    const teardown = useCallback(() => {
        clearInterval(tickRef.current); tickRef.current = null;
        clearTimeout(limitRef.current); limitRef.current = null;
        micRef.current?.close(); micRef.current = null;
        playerRef.current?.close(); playerRef.current = null;
        const ws = wsRef.current;
        wsRef.current = null;
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
            try { ws.close(); } catch { /* already closing */ }
        }
        setSpeaking(false);
        setUserSpeaking(false);
        setPartial({ user: '', assistant: '' });
        setElapsed(0);
    }, []);

    const stop = useCallback(() => {
        stoppingRef.current = true;
        teardown();
        setStatus('idle');
    }, [teardown]);

    useEffect(() => () => teardown(), [teardown]);

    const send = useCallback((payload) => {
        const ws = wsRef.current;
        if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
    }, []);

    const joinItems = (items) => items.map((i) => i.text.trim()).filter(Boolean).join(' ').trim();

    /** Re-emit the question under this turn's id; the widget updates one bubble. */
    const emitUser = useCallback(() => {
        const t = turnRef.current;
        const text = joinItems(t.items);
        if (!text) return;
        t.user = text;
        t.postedUser = true;
        cbRef.current.onUserText?.(text, turnIdRef.current);
    }, []);

    /** A turn ended: post anything not already on screen, then persist the exchange. */
    const flushTurn = useCallback(async () => {
        const { user, assistant, written, postedUser, postedWritten, proposed } = turnRef.current;
        turnRef.current = { user: '', assistant: '', written: '', postedUser: false, postedWritten: false, proposed: false, items: [] };
        setPartial({ user: '', assistant: '' });
        if (!user && !assistant && !written) return;
        // Read postedUser from the SNAPSHOT — the ref above has already been reset, so
        // asking it would always say "not posted yet" and duplicate the question.
        if (!postedUser && user) cbRef.current.onUserText?.(user, turnIdRef.current);
        turnIdRef.current += 1;   // next spoken question gets its own bubble
        // Her written answer is already on screen; her spoken words are the fallback for
        // short exchanges where there was nothing worth writing down. On a proposal turn
        // there is no fallback — the card is the record and her speech stays audio-only.
        const silent = proposed || silentTurnRef.current;
        silentTurnRef.current = false;
        const forChat = silent ? '' : (written || assistant);
        if (!silent && !postedWritten && assistant) cbRef.current.onAssistantText?.(assistant);
        try {
            const { conversation_id: id } = await saveLiveTurn(user, forChat, convoRef.current);
            if (id && id !== convoRef.current) {
                convoRef.current = id;
                cbRef.current.onConversationId?.(id);
            }
        } catch {
            // The spoken exchange already happened; failing to file it must not end the call.
        }
    }, []);

    const answerToolCall = useCallback((callId, result) => {
        // Always answer — a missing function_call_output stalls the session.
        send({
            type: 'conversation.item.create',
            item: { type: 'function_call_output', call_id: callId, output: JSON.stringify(result) },
        });
    }, [send]);

    const handleToolCall = useCallback(async (msg) => {
        const callId = msg.call_id || msg.id;
        let args = {};
        try { args = JSON.parse(msg.arguments || '{}'); } catch { args = {}; }

        // Set BEFORE any await: this response is ending to run a tool, and the turn
        // continues in the next one. A late flag lets response.done flush mid-lookup.
        awaitingFollowUpRef.current = true;

        if (msg.name === WRITE_TO_CHAT) {
            // The screen goes first. Render it now, then let her speak over the top of it.
            const markdown = args.markdown || '';
            turnRef.current.written = markdown;
            if (markdown && !turnRef.current.postedWritten) {
                turnRef.current.postedWritten = true;
                cbRef.current.onAssistantText?.(markdown);
            }
            answerToolCall(callId, { ok: true });
            send({ type: 'response.create' });       // now say the short version
            return;
        }

        const { result, artifact, proposal } = await runLiveTool(msg.name, args);
        if (artifact) cbRef.current.onArtifact?.(artifact);
        answerToolCall(callId, result);

        if (proposal?.plan) {
            // Put the card up, then let her talk over it. The speech is useful — you can
            // keep your eyes on the shop floor — but its transcript is not, because the
            // card beside it already says the same thing.
            turnRef.current.proposed = true;
            cbRef.current.onProposal?.(proposal);
        }
        send({ type: 'response.create' });
    }, [send, answerToolCall]);

    const handleEvent = useCallback((msg) => {
        const type = msg?.type || '';
        if (debug) console.log('[carmen-live]', type, msg);

        if (type === 'session.created') return; // session.update already sent on open
        if (type === 'session.updated') { setStatus('live'); return; }

        if (type === 'input_audio_buffer.speech_started') {
            playerRef.current?.clear();   // barge-in: stop talking over them
            setUserSpeaking(true);
            return;
        }
        if (type === 'input_audio_buffer.speech_stopped') { setUserSpeaking(false); return; }

        if (USER_TRANSCRIPT.has(type)) {
            const text = msg.transcript ?? msg.text ?? msg.delta ?? '';
            const t = turnRef.current;
            const id = msg.item_id || msg.id || null;
            const isDelta = type.endsWith('.delta');

            // One entry per transcription item. xAI re-sends each item's transcript
            // cumulatively as it firms up, so a matching item is REPLACED.
            let entry = id ? t.items.find((i) => i.id === id) : null;
            if (!entry && !id) {
                // No id to match on: treat a transcript that extends the last one as the
                // same utterance growing, rather than a new one to tack on the end.
                const last = t.items[t.items.length - 1];
                if (last && (text.startsWith(last.text) || last.text.startsWith(text))) entry = last;
            }
            if (!entry) {
                entry = { id, text: '' };
                t.items.push(entry);
            }
            entry.text = isDelta ? entry.text + text : text;

            setPartial((p) => ({ ...p, user: joinItems(t.items) }));
            if (!isDelta) emitUser();
            return;
        }

        if (AUDIO_DELTA.has(type)) {
            const b64 = msg.delta || msg.audio;
            if (b64) playerRef.current?.push(b64);
            return;
        }
        if (TEXT_DELTA.has(type)) {
            turnRef.current.assistant += (msg.delta || msg.text || '');
            setPartial((p) => ({ ...p, assistant: turnRef.current.assistant }));
            return;
        }
        if (TEXT_DONE.has(type)) {
            if (msg.transcript) turnRef.current.assistant = msg.transcript;
            setPartial((p) => ({ ...p, assistant: turnRef.current.assistant }));
            return;
        }

        if (type === 'response.function_call_arguments.done') { handleToolCall(msg); return; }
        if (type === 'response.done') {
            if (awaitingFollowUpRef.current) {
                // That response only ended so a lookup could run; the answer is still coming.
                awaitingFollowUpRef.current = false;
                return;
            }
            flushTurn();
            return;
        }

        if (type === 'error') {
            const detail = msg.error?.message || msg.message || 'The live session hit an error.';
            setError(detail);
            setStatus('error');
            teardown();
        }
    }, [debug, handleToolCall, flushTurn, teardown, emitUser]);

    /** Tell her a card was confirmed (or cancelled) so she can say so out loud.
     *
     * This is after-the-fact narration, not permission: the write has already happened
     * on the server by the time this runs.
     */
    const notifyApplied = useCallback((summary) => {
        if (!summary) return;
        silentTurnRef.current = true;   // she says it landed; the card already shows it
        send({
            type: 'conversation.item.create',
            item: {
                type: 'message',
                role: 'user',
                content: [{ type: 'input_text', text: `[system] ${summary}` }],
            },
        });
        send({ type: 'response.create' });
    }, [send]);

    const start = useCallback(async () => {
        if (status === 'connecting' || status === 'live') return;
        if (!supported) {
            setError('This browser can’t run a live call (needs AudioWorklet + WebSocket).');
            setStatus('error');
            return;
        }
        setError('');
        setStatus('connecting');
        stoppingRef.current = false;
        turnRef.current = { user: '', assistant: '', written: '', postedUser: false, postedWritten: false, proposed: false, items: [] };
        awaitingFollowUpRef.current = false;

        let broker;
        try {
            broker = await startLiveSession();
        } catch (err) {
            setError(err?.response?.data?.error || 'Couldn’t start a live session.');
            setStatus('error');
            return;
        }

        let ws;
        try {
            ws = new WebSocket(broker.url, [`xai-client-secret.${broker.token}`]);
        } catch {
            setError('Couldn’t open the live connection.');
            setStatus('error');
            return;
        }
        wsRef.current = ws;

        ws.onopen = async () => {
            send({ type: 'session.update', session: broker.session });
            playerRef.current = new PcmPlayer({ onStateChange: setSpeaking });
            const mic = new MicCapture({
                onChunk: (b64) => send({ type: 'input_audio_buffer.append', audio: b64 }),
            });
            micRef.current = mic;
            try {
                await mic.start();
            } catch (e) {
                setError(e?.name === 'NotAllowedError'
                    ? 'Microphone access was blocked.'
                    : 'Couldn’t open the microphone.');
                setStatus('error');
                teardown();
                return;
            }
            setStatus('live');
            tickRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);
            // Hard stop, so an open mic in a forgotten tab can't bill all afternoon.
            limitRef.current = setTimeout(stop, (broker.max_session_seconds || 900) * 1000);
        };

        ws.onmessage = (e) => {
            if (typeof e.data !== 'string') return; // binary transport not used
            let msg;
            try { msg = JSON.parse(e.data); } catch { return; }
            handleEvent(msg);
        };

        ws.onerror = () => {
            if (stoppingRef.current) return;
            setError('The live connection dropped.');
            setStatus('error');
            teardown();
        };

        ws.onclose = () => {
            if (stoppingRef.current) return;
            teardown();
            setStatus((s) => (s === 'error' ? s : 'idle'));
        };
    }, [status, supported, send, handleEvent, teardown, stop]);

    return { supported, status, error, speaking, userSpeaking, partial, elapsed,
             start, stop, notifyApplied };
}
