import { useCallback, useEffect, useState } from 'react';
import {
    clearMessages as clearMessagesApi,
    fetchMessages,
    sendMessage as sendMessageApi,
    sendVoiceMessage as sendVoiceMessageApi,
} from '../services/bananaBoyApi';

export function useBananaBoyChat(enabled) {
    const [messages, setMessages] = useState([]);
    const [loading, setLoading] = useState(false);
    const [sending, setSending] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (!enabled) return undefined;
        let cancelled = false;
        setLoading(true);
        fetchMessages()
            .then((rows) => {
                if (!cancelled) setMessages(rows);
            })
            .catch((err) => {
                if (!cancelled) setError(err.response?.data?.error || err.message);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => { cancelled = true; };
    }, [enabled]);

    const send = useCallback(async (text) => {
        const trimmed = text.trim();
        if (!trimmed || sending) return;

        const optimistic = {
            id: `pending-${Date.now()}`,
            role: 'user',
            content: trimmed,
            created_at: new Date().toISOString(),
            pending: true,
        };
        setMessages((prev) => [...prev, optimistic]);
        setSending(true);
        setError(null);

        try {
            const reply = await sendMessageApi(trimmed);
            setMessages((prev) => [
                ...prev.map((m) => (m.id === optimistic.id ? { ...m, pending: false } : m)),
                reply,
            ]);
        } catch (err) {
            const msg = err.response?.data?.error || err.message;
            setError(msg);
            setMessages((prev) =>
                prev.map((m) => (m.id === optimistic.id ? { ...m, pending: false, failed: true } : m))
            );
        } finally {
            setSending(false);
        }
    }, [sending]);

    const sendVoice = useCallback(async (audioBlob, filename) => {
        if (!audioBlob || sending) return null;

        const pendingId = `pending-voice-${Date.now()}`;
        const optimistic = {
            id: pendingId,
            role: 'user',
            content: '🎤 …',
            created_at: new Date().toISOString(),
            pending: true,
        };
        setMessages((prev) => [...prev, optimistic]);
        setSending(true);
        setError(null);

        try {
            const data = await sendVoiceMessageApi(audioBlob, filename);
            const userTurn = {
                id: `voice-user-${data.message.id}`,
                role: 'user',
                content: data.transcript,
                created_at: new Date().toISOString(),
            };
            const assistantWithUsage = { ...data.message, usage: data.usage };
            setMessages((prev) => [
                ...prev.filter((m) => m.id !== pendingId),
                userTurn,
                assistantWithUsage,
            ]);
            return data;
        } catch (err) {
            const msg = err.response?.data?.error || err.message;
            setError(msg);
            setMessages((prev) =>
                prev.map((m) => (m.id === pendingId ? { ...m, pending: false, failed: true } : m))
            );
            return null;
        } finally {
            setSending(false);
        }
    }, [sending]);

    const clear = useCallback(async () => {
        try {
            await clearMessagesApi();
            setMessages([]);
            setError(null);
        } catch (err) {
            setError(err.response?.data?.error || err.message);
        }
    }, []);

    return { messages, loading, sending, error, send, sendVoice, clear };
}
