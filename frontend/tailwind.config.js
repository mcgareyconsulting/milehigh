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
                // Calibri is the only typeface in the app, and it matches the print
                // PDFs (both embed it as Carlito from frontend/public/fonts/*.ttf).
                // body already sets the stack in index.css; this theme key makes the
                // font-sans utility use the same one. Carlito is the metric-compatible
                // stand-in for machines without Calibri — see the note in index.css.
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
                // `font-mono` is no longer a second typeface — it resolves to Calibri
                // like everything else. The ~100 call sites keep the class as the
                // marker for the role the design handoff gave it (numbers, dates, ids,
                // version strings), which is why it stays a distinct key rather than
                // being stripped out of the components.
                //
                // What that role actually needed was digits on one fixed advance so
                // columns of numbers stack. Calibri and Carlito already draw them that
                // way; `tnum` only matters if the reader has neither and falls through
                // to a system face with proportional figures.
                mono: [
                    [
                        'Calibri',
                        'Carlito',
                        '-apple-system',
                        'BlinkMacSystemFont',
                        'Segoe UI',
                        'Roboto',
                        'Helvetica Neue',
                        'sans-serif',
                    ],
                    { fontFeatureSettings: '"tnum"' },
                ],
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

