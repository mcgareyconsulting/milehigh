/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Push-to-talk mic capture for the Carmen window. Wraps MediaRecorder, picks a
 *          container xAI's transcriber accepts, and tracks elapsed time / permission state.
 * exports:
 *   useVoiceRecorder: default. ({ maxSeconds, onClip }) -> { supported, recording, seconds,
 *                     error, start, stop, cancel }.
 * imports_from: [react]
 * imported_by: [components/BBChatWidget.jsx]
 * invariants:
 *   - The mic stream is always stopped on stop/cancel/unmount — no lingering recording dot.
 *   - onClip fires only for a non-empty clip that was stopped (not cancelled).
 *   - Recording auto-stops at maxSeconds so a forgotten mic can't post a huge upload.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

// Preference order: containers xAI's speech-to-text lists outright come first; Chrome's
// WebM/Opus is last because it is accepted as a Matroska profile rather than by name.
const CANDIDATES = [
    { mime: 'audio/mp4', ext: 'mp4' },
    { mime: 'audio/ogg;codecs=opus', ext: 'ogg' },
    { mime: 'audio/webm;codecs=opus', ext: 'webm' },
    { mime: 'audio/webm', ext: 'webm' },
];

function pickFormat() {
    if (typeof MediaRecorder === 'undefined') return null;
    for (const c of CANDIDATES) {
        if (MediaRecorder.isTypeSupported?.(c.mime)) return c;
    }
    return { mime: '', ext: 'webm' }; // let the browser choose its default
}

export default function useVoiceRecorder({ maxSeconds = 120, onClip } = {}) {
    const [recording, setRecording] = useState(false);
    const [seconds, setSeconds] = useState(0);
    const [error, setError] = useState('');
    const recorderRef = useRef(null);
    const streamRef = useRef(null);
    const chunksRef = useRef([]);
    const cancelledRef = useRef(false);
    const tickRef = useRef(null);
    const onClipRef = useRef(onClip);
    onClipRef.current = onClip;

    const supported = typeof navigator !== 'undefined'
        && !!navigator.mediaDevices?.getUserMedia
        && typeof MediaRecorder !== 'undefined';

    const teardown = useCallback(() => {
        clearInterval(tickRef.current);
        tickRef.current = null;
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        recorderRef.current = null;
        setRecording(false);
        setSeconds(0);
    }, []);

    useEffect(() => () => teardown(), [teardown]);

    const stop = useCallback(() => {
        const rec = recorderRef.current;
        if (!rec || rec.state === 'inactive') return;
        cancelledRef.current = false;
        rec.stop();
    }, []);

    const cancel = useCallback(() => {
        const rec = recorderRef.current;
        cancelledRef.current = true;
        if (rec && rec.state !== 'inactive') rec.stop();
        else teardown();
    }, [teardown]);

    const start = useCallback(async () => {
        if (recording) return;
        setError('');
        if (!supported) {
            setError('This browser can’t record audio.');
            return;
        }
        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
            });
        } catch (e) {
            setError(e?.name === 'NotAllowedError'
                ? 'Microphone access was blocked.'
                : 'Couldn’t open the microphone.');
            return;
        }

        const fmt = pickFormat();
        let rec;
        try {
            rec = new MediaRecorder(stream, fmt.mime ? { mimeType: fmt.mime } : undefined);
        } catch {
            stream.getTracks().forEach((t) => t.stop());
            setError('This browser can’t record audio.');
            return;
        }

        chunksRef.current = [];
        cancelledRef.current = false;
        streamRef.current = stream;
        recorderRef.current = rec;

        rec.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
        };
        rec.onstop = () => {
            const chunks = chunksRef.current;
            chunksRef.current = [];
            const wasCancelled = cancelledRef.current;
            teardown();
            if (wasCancelled || chunks.length === 0) return;
            const type = rec.mimeType || fmt.mime || 'audio/webm';
            const blob = new Blob(chunks, { type });
            if (blob.size > 0) onClipRef.current?.(blob, `clip.${fmt.ext}`);
        };

        rec.start();
        setRecording(true);
        setSeconds(0);
        tickRef.current = setInterval(() => {
            setSeconds((s) => {
                const next = s + 1;
                if (next >= maxSeconds) stop();
                return next;
            });
        }, 1000);
    }, [recording, supported, maxSeconds, stop, teardown]);

    return { supported, recording, seconds, error, start, stop, cancel };
}
