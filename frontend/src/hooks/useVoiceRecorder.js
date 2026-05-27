import { useCallback, useEffect, useRef, useState } from 'react';

const PREFERRED_MIME = 'audio/webm;codecs=opus';

function pickMimeType() {
    if (typeof MediaRecorder === 'undefined') return null;
    if (MediaRecorder.isTypeSupported(PREFERRED_MIME)) return PREFERRED_MIME;
    if (MediaRecorder.isTypeSupported('audio/webm')) return 'audio/webm';
    if (MediaRecorder.isTypeSupported('audio/mp4')) return 'audio/mp4';
    return '';
}

export function useVoiceRecorder() {
    const [isRecording, setIsRecording] = useState(false);
    const [error, setError] = useState(null);
    const recorderRef = useRef(null);
    const streamRef = useRef(null);
    const chunksRef = useRef([]);
    const stopResolveRef = useRef(null);

    const releaseStream = useCallback(() => {
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((t) => t.stop());
            streamRef.current = null;
        }
    }, []);

    useEffect(() => releaseStream, [releaseStream]);

    const start = useCallback(async () => {
        if (recorderRef.current) return;
        setError(null);
        if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
            setError('Voice recording is not supported in this browser');
            return;
        }
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            streamRef.current = stream;
            const mimeType = pickMimeType();
            const recorder = mimeType
                ? new MediaRecorder(stream, { mimeType })
                : new MediaRecorder(stream);
            chunksRef.current = [];
            recorder.ondataavailable = (e) => {
                if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
            };
            recorder.onstop = () => {
                const type = recorder.mimeType || 'audio/webm';
                const blob = new Blob(chunksRef.current, { type });
                chunksRef.current = [];
                releaseStream();
                recorderRef.current = null;
                setIsRecording(false);
                if (stopResolveRef.current) {
                    const resolve = stopResolveRef.current;
                    stopResolveRef.current = null;
                    resolve(blob);
                }
            };
            recorderRef.current = recorder;
            recorder.start();
            setIsRecording(true);
        } catch (err) {
            setError(err?.message || 'Could not access microphone');
            releaseStream();
        }
    }, [releaseStream]);

    const stop = useCallback(() => {
        const recorder = recorderRef.current;
        if (!recorder) return Promise.resolve(null);
        if (recorder.state === 'inactive') return Promise.resolve(null);
        return new Promise((resolve) => {
            stopResolveRef.current = resolve;
            try {
                recorder.stop();
            } catch {
                stopResolveRef.current = null;
                releaseStream();
                recorderRef.current = null;
                setIsRecording(false);
                resolve(null);
            }
        });
    }, [releaseStream]);

    return { isRecording, error, start, stop };
}
