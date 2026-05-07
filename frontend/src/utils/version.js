// Build identifier injected by Vite at build time (see vite.config.js `define`).
// In dev: short git SHA from `git rev-parse`. In Render builds: RENDER_GIT_COMMIT.
// Falls back to "dev" if neither is available (e.g. unit-test environment).
export const CLIENT_VERSION =
  typeof __BUILD_SHA__ !== 'undefined' ? __BUILD_SHA__ : 'dev';
