// Shared API configuration
// Automatically detect dev vs production mode
// Dev mode (npm run dev): Use Flask backend at localhost:8000
// Device mode (npm run dev:ipad, sets VITE_PROXY_API): same origin — Vite proxies API
//   calls to Flask (see vite.config.js), so the app works from a phone/tablet on the LAN.
// Production mode (npm run build): Use same origin (empty string)
// Can override with VITE_API_URL env var if needed
export const API_BASE_URL =
    import.meta.env.VITE_API_URL ||
    (import.meta.env.VITE_PROXY_API
        ? '' // same-origin; requests route through Vite's dev proxy to Flask
        : import.meta.env.DEV
            ? 'http://localhost:8000'
            : '');

