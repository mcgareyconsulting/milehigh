// Shared API configuration
// Automatically detect dev vs production mode
// Dev mode (npm run dev): Use Flask backend at localhost:8000
// Production mode (npm run build): Use same origin (empty string)
// Can override with VITE_API_URL env var if needed
export const API_BASE_URL = import.meta.env.VITE_API_URL ||
    (import.meta.env.DEV ? 'http://localhost:8000' : '');

