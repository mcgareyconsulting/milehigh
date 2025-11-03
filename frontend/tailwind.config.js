/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
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

