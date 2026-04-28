import { useCallback, useEffect, useState } from 'react';
import {
    clearMessages as clearMessagesApi,
    fetchMessages,
    sendMessage as sendMessageApi,
} from '../services/bananaBoyApi';

export function useBananaBoyChat(enabled) {
    const [messages, setMessages] = useState([]);
    const [loading, setLoading] = useState(false);
    const [sending, setSending] = useState(false);
    const [error, setError] = useState(null);
    const [hasFetched, setHasFetched] = useState(false);

    useEffect(() => {
        if (!enabled || hasFetched) return;
        let cancelled = false;
        setLoading(true);
        fetchMessages()
            .then((rows) => {
                if (cancelled) return;
                setMessages(rows);
                setHasFetched(true);
            })
            .catch((err) => {
                if (cancelled) return;
                setError(err.response?.data?.error || err.message);
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });
        return () => { cancelled = true; };
    }, [enabled, hasFetched]);

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

    const clear = useCallback(async () => {
        try {
            await clearMessagesApi();
            setMessages([]);
            setError(null);
        } catch (err) {
            setError(err.response?.data?.error || err.message);
        }
    }, []);

    return { messages, loading, sending, error, send, clear };
}
