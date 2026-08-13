/** @type {import('tailwindcss').Config} */
export default {
    darkMode: 'class',
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            screens: {
                '3xl': '1920px',
            },
            keyframes: {
                slideInRight: {
                    '0%': { transform: 'translateX(100%)', opacity: '0' },
                    '100%': { transform: 'translateX(0)', opacity: '1' },
                },
                slideOutRight: {
                    '0%': { transform: 'translateX(0)', opacity: '1' },
                    '100%': { transform: 'translateX(100%)', opacity: '0' },
                },
            },
            animation: {
                'slide-in-right': 'slideInRight 0.3s ease-out',
                'slide-out-right': 'slideOutRight 0.3s ease-in forwards',
            },
            fontFamily: {
                // Matches the Job Log print PDF (jsPDF embeds Carlito / IBMPlexMono
                // from frontend/public/fonts/*.ttf). body already sets the stack in
                // index.css; these theme keys make font-sans / font-mono utilities use
                // the same faces. Carlito is the metric-compatible stand-in for Calibri
                // on machines that don't have it — see the note in index.css.
                sans: [
                    'Calibri',
                    'Carlito',
                    '-apple-system',
                    'BlinkMacSystemFont',
                    'Segoe UI',
                    'Roboto',
                    'Oxygen',
                    'Ubuntu',
                    'Cantarell',
                    'Helvetica Neue',
                    'sans-serif',
                ],
                // Numbers, dates, ids and version strings, per the design handoff.
                mono: ['IBM Plex Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
            },
            fontSize: {
                // The handoff's table scale. Tailwind's text-xs (12px) and text-sm
                // (14px) straddle it, and rounding to either visibly breaks the
                // match to the print, so the exact steps get their own names.
                'jl': ['12.5px', { lineHeight: '1.2' }],
                'jl-compact': ['12px', { lineHeight: '1.2' }],
                'jl-2': ['11.5px', { lineHeight: '1.2' }],
                'jl-3': ['10.5px', { lineHeight: '1.15' }],
                'jl-head': ['12px', { lineHeight: '1.15' }],
                'jl-label': ['11px', { lineHeight: '1.2', letterSpacing: '.06em' }],
            },
            colors: {
                // Design tokens from src/styles/tokens.css. Each resolves through a
                // CSS var, so `bg-surface` is already correct in both themes and
                // must NOT be paired with a `dark:` variant — doing so would pin
                // one theme's literal value into the other.
                'canvas': 'var(--bg)',
                'surface': 'var(--surface)',
                'surface-2': 'var(--surface-2)',
                'head-bg': 'var(--head-bg)',
                'hairline': 'var(--border)',
                'hairline-strong': 'var(--border-strong)',
                'grid': 'var(--grid)',
                'ink': 'var(--text)',
                'ink-2': 'var(--text-2)',
                'ink-3': 'var(--text-3)',
                'rail': 'var(--rail-bg)',
                'rail-fg': 'var(--rail-fg)',
                'rail-active': 'var(--rail-active)',
                'rail-border': 'var(--rail-border)',
                'brand': 'var(--accent)',
                'brand-soft': 'var(--accent-soft)',
                'brand-ink': 'var(--accent-ink)',
                'input-bg': 'var(--input-bg)',
                'accent': {
                    '50': '#e6ebf5',
                    '100': '#ccd7eb',
                    '200': '#99afe7',
                    '300': '#6687d3',
                    '400': '#335fbf',
                    '500': '#264093',
                    '600': '#1e336e',
                    '700': '#172649',
                    '800': '#0f1924',
                    '900': '#080d12',
                },
            },
        },
    },
    plugins: [],
}

