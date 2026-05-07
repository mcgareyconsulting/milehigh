import { API_BASE_URL } from './api';
import { CLIENT_VERSION } from './version';

// Network failures resolve to "not stale" so transient outages don't show a false-positive banner.
export async function checkVersion() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/version`, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });
    if (!res.ok) return { stale: false, server: null };
    const data = await res.json();
    const server = data?.version || null;
    if (!server || server === CLIENT_VERSION) return { stale: false, server };
    return { stale: true, server };
  } catch {
    return { stale: false, server: null };
  }
}
