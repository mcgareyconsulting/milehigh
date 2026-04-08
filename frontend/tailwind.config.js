/** @type {import('tailwindcss').Config} */
export default {
    darkMode: 'class',
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
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
            colors: {
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

