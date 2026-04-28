import { useState, useEffect, useCallback } from 'react';
import ChatModal from './ChatModal';
import { checkAuth } from '../../utils/auth';

export default function ChatBubble() {
    const [open, setOpen] = useState(false);
    const [user, setUser] = useState(null);

    const refreshUser = useCallback(async () => {
        const u = await checkAuth();
        setUser(u);
    }, []);

    useEffect(() => {
        refreshUser();
    }, [refreshUser]);

    return (
        <>
            {open && <ChatModal user={user} onClose={() => setOpen(false)} onUserChange={refreshUser} />}
            <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-label={open ? 'Close Banana Boy' : 'Open Banana Boy'}
                title="Banana Boy"
                className="fixed bottom-6 right-6 z-50 w-12 h-12 rounded-full bg-accent-500 hover:bg-accent-600 text-white shadow-lg flex items-center justify-center focus:outline-none focus:ring-2 focus:ring-accent-400 focus:ring-offset-2 dark:focus:ring-offset-slate-900 transition-transform hover:scale-105"
            >
                {open ? (
                    <span aria-hidden="true" className="text-xl leading-none">×</span>
                ) : (
                    <img
                        src="/bananas-svgrepo-com.svg"
                        alt=""
                        draggable={false}
                        className="h-7 w-7"
                    />
                )}
            </button>
        </>
    );
}
