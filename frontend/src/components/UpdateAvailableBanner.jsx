import { useEffect, useState } from 'react';
import { checkVersion } from '../utils/versionCheck';

export default function UpdateAvailableBanner() {
  const [stale, setStale] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    const runCheck = async () => {
      const { stale: isStale } = await checkVersion();
      setStale(isStale);
      if (isStale) setDismissed(false);
    };
    runCheck();
    const onVisibility = () => {
      if (document.visibilityState === 'visible') runCheck();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);

  if (!stale || dismissed) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="update-available-banner"
      className="fixed top-0 inset-x-0 z-50 bg-amber-50 dark:bg-amber-900/40 border-b-2 border-amber-500 text-amber-900 dark:text-amber-100 shadow-sm"
    >
      <div className="max-w-7xl mx-auto px-4 py-2 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-sm">
          <span aria-hidden="true">🔄</span>
          <span className="font-semibold">A new version is available.</span>
          <span className="text-amber-800 dark:text-amber-200">
            Reload to pick up the latest changes.
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="px-3 py-1 text-sm font-medium rounded-md bg-amber-500 hover:bg-amber-600 text-white shadow-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
          >
            Reload
          </button>
          <button
            type="button"
            onClick={() => setDismissed(true)}
            aria-label="Dismiss update notification"
            className="px-2 py-1 text-sm rounded-md text-amber-800 dark:text-amber-200 hover:bg-amber-100 dark:hover:bg-amber-800/40"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
