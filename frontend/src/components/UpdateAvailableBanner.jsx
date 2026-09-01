/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Transient "a new version is deployed, reload" notice, rendered above the app shell.
 * exports:
 *   UpdateAvailableBanner: Fixed top-centre pill; polls checkVersion() on mount and on tab focus.
 * imports_from: [react, ../utils/versionCheck]
 * imported_by: [../App.jsx]
 * invariants:
 *   - It is an OVERLAY, not in flow — nothing below it reflows, so it must not sit under the
 *     upper-right chrome (notification pod + Carmen launcher). It is a centred pill, and the
 *     wrapper reserves --notif-pod-gutter on the right so centring stays clear of that corner
 *     in Left Sidebar Mode. Do not make it full-bleed again.
 *   - z sits above the top bar and the pod (both z-50) but below their dropdowns/toasts (z-60+),
 *     so an open notification panel still wins.
 *   - The wrapper is pointer-events-none so the strip either side of the pill never eats clicks
 *     on the chrome underneath.
 *   - Dismissal is keyed to the SERVER VERSION that was showing, and kept in sessionStorage.
 *     Re-confirming the same pending version (which happens on every tab return) must never
 *     resurrect a banner the user already waved off; only a NEW server version brings it back.
 */
import { useEffect, useState } from 'react';
import { checkVersion } from '../utils/versionCheck';

// Per-tab, not localStorage: a dismissal is a "not right now", scoped to this sitting.
const DISMISSED_KEY = 'mhmw:update-banner-dismissed-version';

const readDismissed = () => {
  try {
    return sessionStorage.getItem(DISMISSED_KEY);
  } catch {
    return null; // private mode / storage disabled — fall back to in-memory only
  }
};

const writeDismissed = (version) => {
  try {
    sessionStorage.setItem(DISMISSED_KEY, version);
  } catch {
    /* in-memory state still holds for the life of this mount */
  }
};

export default function UpdateAvailableBanner() {
  const [stale, setStale] = useState(false);
  const [serverVersion, setServerVersion] = useState(null);
  const [dismissedVersion, setDismissedVersion] = useState(readDismissed);

  useEffect(() => {
    const runCheck = async () => {
      const { stale: isStale, server } = await checkVersion();
      setStale(isStale);
      setServerVersion(server ?? null);
    };
    runCheck();
    const onVisibility = () => {
      if (document.visibilityState === 'visible') runCheck();
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, []);

  // `server` is always non-null when stale (see checkVersion), but key defensively so a
  // malformed response can still be dismissed rather than sticking forever.
  const pendingVersion = serverVersion || 'unknown';

  const dismiss = () => {
    setDismissedVersion(pendingVersion);
    writeDismissed(pendingVersion);
  };

  if (!stale || dismissedVersion === pendingVersion) return null;

  return (
    <div
      data-testid="update-available-banner-wrap"
      className="fixed top-2 inset-x-0 z-[55] flex justify-center pointer-events-none pl-3"
      style={{ paddingRight: 'calc(var(--notif-pod-gutter, 0px) + 0.75rem)' }}
    >
      <div
        role="status"
        aria-live="polite"
        data-testid="update-available-banner"
        className="pointer-events-auto max-w-full flex items-center gap-3 pl-4 pr-2 py-1.5 rounded-full
                   bg-amber-50 dark:bg-amber-900/90 border border-amber-400 dark:border-amber-500
                   text-amber-900 dark:text-amber-100 shadow-lg backdrop-blur-sm"
      >
        <div className="flex items-center gap-2 min-w-0 text-sm">
          <span aria-hidden="true">🔄</span>
          <span className="font-semibold whitespace-nowrap">A new version is available.</span>
          <span className="hidden sm:inline text-amber-800 dark:text-amber-200 whitespace-nowrap">
            Reload to pick up the latest changes.
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="px-3 py-1 text-sm font-medium rounded-full bg-amber-500 hover:bg-amber-600 text-white shadow-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
          >
            Reload
          </button>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Dismiss update notification"
            className="px-2 py-1 text-sm rounded-full text-amber-800 dark:text-amber-200 hover:bg-amber-100 dark:hover:bg-amber-800/40"
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
