/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execSync } from 'node:child_process'

function resolveBuildSha() {
  const renderSha = process.env.RENDER_GIT_COMMIT
  if (renderSha) return renderSha.slice(0, 7)
  try {
    return execSync('git rev-parse --short=7 HEAD', { stdio: ['ignore', 'pipe', 'ignore'] })
      .toString()
      .trim()
  } catch {
    return 'dev'
  }
}

// Flask (backend) route prefixes. Used only for on-device testing via `npm run dev:ipad`,
// where the frontend is served same-origin and Vite forwards these calls to Flask. In a
// normal `npm run dev` the frontend hits Flask directly (localhost:8000) and these stay inert.
const BACKEND_PREFIXES = ['/api', '/brain', '/admin', '/procore', '/trello', '/lake']

// SPA-aware proxy: real browser navigations (Accept: text/html) fall through to Vite so
// client routes that share a prefix with an API — e.g. the page `/admin/fc-collection` vs the
// API `/admin/fc-collection` — still load. Only XHR/fetch API calls get proxied to Flask.
const deviceProxy = Object.fromEntries(
  BACKEND_PREFIXES.map((prefix) => [
    prefix,
    {
      target: 'http://localhost:8000',
      changeOrigin: false,
      bypass(req) {
        if (req.headers.accept && req.headers.accept.includes('text/html')) {
          return req.url
        }
      },
    },
  ]),
)

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // `npm run dev:ipad` adds `--host` to expose this on the LAN/tailnet for tablet testing.
    proxy: deviceProxy,
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  },
  // Use relative paths for production (served from Flask root)
  base: '/',
  define: {
    __BUILD_SHA__: JSON.stringify(resolveBuildSha()),
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
  },
})