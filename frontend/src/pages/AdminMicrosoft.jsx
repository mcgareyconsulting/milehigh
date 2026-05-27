import { useEffect, useMemo, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
    buildMicrosoftLinkUrl,
    disconnectMicrosoft,
    messageForMicrosoftError,
} from '../services/microsoftAuthApi';
import { checkAuth } from '../utils/auth';

export default function AdminMicrosoft() {
    const navigate = useNavigate();
    const location = useLocation();
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [disconnecting, setDisconnecting] = useState(false);
    const [actionError, setActionError] = useState(null);

    const params = useMemo(
        () => new URLSearchParams(location.search),
        [location.search],
    );
    const msErrorCode = params.get('ms_error');
    const msErrorMsg = msErrorCode ? messageForMicrosoftError(msErrorCode) : null;
    const justConnected = params.get('outlook_connected') === '1';

    const refresh = async () => {
        const u = await checkAuth();
        setUser(u);
        setLoading(false);
    };

    useEffect(() => {
        refresh();
    }, []);

    useEffect(() => {
        if (justConnected) {
            refresh();
            const next = location.pathname;
            navigate(next, { replace: true });
        }
    }, [justConnected, location.pathname, navigate]);

    const handleConnect = () => {
        const next = location.pathname;
        window.location.href = buildMicrosoftLinkUrl(next);
    };

    const handleDisconnect = async () => {
        if (disconnecting) return;
        setActionError(null);
        setDisconnecting(true);
        try {
            await disconnectMicrosoft();
            await refresh();
        } catch (err) {
            setActionError(err.message || 'Disconnect failed.');
        } finally {
            setDisconnecting(false);
        }
    };

    if (loading) {
        return (
            <div className="min-h-[40vh] flex items-center justify-center text-gray-600 dark:text-slate-400">
                Loading...
            </div>
        );
    }

    if (!user) {
        return (
            <div className="max-w-2xl mx-auto px-6 py-10 text-gray-700 dark:text-slate-200">
                Please <button onClick={() => navigate('/login')} className="underline">log in</button> first.
            </div>
        );
    }

    const linked = !!user.outlook_linked;

    return (
        <div className="max-w-2xl mx-auto px-6 py-10">
            <h1 className="text-2xl font-semibold text-gray-900 dark:text-slate-100 mb-2">
                Microsoft / Outlook
            </h1>
            <p className="text-sm text-gray-600 dark:text-slate-400 mb-6">
                Connect your Microsoft account so Banana Boy can read your Outlook
                inbox during a report deep dive. Read-only — Banana Boy never
                sends mail from Outlook.
            </p>

            {justConnected && (
                <div className="mb-4 px-4 py-3 rounded-lg bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300 text-sm">
                    Outlook connected.
                </div>
            )}
            {msErrorMsg && (
                <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300 text-sm">
                    {msErrorMsg}
                </div>
            )}
            {actionError && (
                <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300 text-sm">
                    {actionError}
                </div>
            )}

            <div className="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-5">
                <div className="flex items-start justify-between gap-4">
                    <div>
                        <div className="text-sm font-medium text-gray-900 dark:text-slate-100">
                            Status
                        </div>
                        <div className="mt-1 text-sm text-gray-700 dark:text-slate-300">
                            {linked ? (
                                <>
                                    <span className="inline-flex items-center gap-1.5 text-green-700 dark:text-green-400 font-medium">
                                        <span className="w-2 h-2 rounded-full bg-green-500" />
                                        Connected
                                    </span>
                                    {user.outlook_email && (
                                        <span className="ml-2 text-gray-500 dark:text-slate-400">
                                            as {user.outlook_email}
                                        </span>
                                    )}
                                </>
                            ) : (
                                <span className="inline-flex items-center gap-1.5 text-gray-500 dark:text-slate-400">
                                    <span className="w-2 h-2 rounded-full bg-gray-400" />
                                    Not connected
                                </span>
                            )}
                        </div>
                    </div>
                    <div className="flex gap-2">
                        <button
                            type="button"
                            onClick={handleConnect}
                            className="px-4 py-2 text-sm font-medium rounded-lg bg-accent-500 text-white hover:bg-accent-600 transition-colors"
                        >
                            {linked ? 'Reconnect' : 'Connect Outlook'}
                        </button>
                        {linked && (
                            <button
                                type="button"
                                onClick={handleDisconnect}
                                disabled={disconnecting}
                                className="px-4 py-2 text-sm font-medium rounded-lg border border-red-200 dark:border-red-800 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors"
                            >
                                {disconnecting ? 'Disconnecting…' : 'Disconnect'}
                            </button>
                        )}
                    </div>
                </div>
            </div>

            <p className="mt-4 text-xs text-gray-500 dark:text-slate-500">
                Tokens are stored on the server only. Disconnecting deletes the
                stored refresh token; reconnecting requires a fresh consent.
            </p>
        </div>
    );
}
