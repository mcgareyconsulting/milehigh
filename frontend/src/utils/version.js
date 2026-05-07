// __BUILD_SHA__ is replaced at build time by Vite's `define` (see vite.config.js).
export const CLIENT_VERSION =
  typeof __BUILD_SHA__ !== 'undefined' ? __BUILD_SHA__ : 'dev';
