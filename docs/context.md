# Cache & Build Versioning Audit + Implementation Plan

## Context

We have a production web app with ~30 concurrent users in a B2B setting. We ship features frequently (multiple times per week). Users keep tabs open for days or weeks without refreshing, and we recently had a user hitting 404s and rendering print data in an old format because their browser was running a 3-week-old bundle. Hard refresh fixed it.

We need to solve this properly. The goal is **stale clients should detect they're stale and prompt the user to reload — without forcing sign-outs and without disrupting active work**.

This task has two phases. Do **Phase 1 only** and report back before starting Phase 2.

---

## Phase 1: Audit (read-only, no code changes)

Investigate the current state of the codebase and infrastructure with respect to caching and client versioning. Produce a written report covering:

### 1. Cache headers on the HTML shell
- What `Cache-Control` headers are set on `index.html` (or the equivalent root document)?
- Is this set in the app, the reverse proxy, the CDN, or somewhere else?
- If we're behind CloudFront or another CDN, what does the behavior config say for the root document vs. hashed assets?
- Check both the origin response and the CDN response — they can differ.

### 2. Bundle hashing
- Are JS/CSS bundles content-hashed (e.g. `main.a3f2c1.js`)?
- What `Cache-Control` is set on hashed bundles? (Should be `immutable`, long max-age.)
- What bundler are we using and where is the hashing config?

### 3. Service worker
- Is there a service worker registered? If yes, where is it configured and what's its caching strategy?
- If there's no service worker, note that — we don't need to add one.

### 4. Existing version surface
- Is there any current concept of a build version exposed to the client (env var, build-time constant, meta tag, endpoint)?
- Does the API send or check any version header?
- Is there anything in localStorage or sessionStorage related to versioning?

### 5. Deployment pipeline
- How are deploys triggered and what artifacts get built? (Quick summary — we mostly care about whether a git SHA or build ID is available at build time.)
- Are old bundles purged from the CDN/origin on deploy, or do they linger? (This matters: if old bundles 404, that's our user's "404s" symptom.)

### 6. Root cause hypothesis
Based on the above, write a short hypothesis for why our user was running a 3-week-old bundle. Be specific — e.g. "the HTML shell is cached for 24h at the CDN edge AND the user's browser is also caching it, so the chain of stale-bundle references compounds" vs. "HTML is no-cache but the service worker is serving the old shell from cache."

**Stop here. Do not modify any code yet.** Report findings and wait for go-ahead before Phase 2.

---

## Phase 2: Implementation plan + execution

After I review Phase 1, you'll implement the following (we'll adjust based on what you find):

### 2a. Fix cache headers
- `index.html` (or root document): `Cache-Control: no-cache` — must always revalidate.
- Hashed bundles: `Cache-Control: public, max-age=31536000, immutable`.
- Apply at the correct layer (origin, CDN, or both — depends on what Phase 1 finds).
- Verify old bundles remain available at their hashed URLs for some grace period after deploy (users mid-session shouldn't 404 on chunks).

### 2b. Build version exposure
- Embed the git SHA (short form, e.g. first 7 chars) into the client bundle at build time as a constant.
- Expose a `/api/version` (or equivalent) endpoint on the backend that returns `{ version: "<sha>", releasedAt: "<iso8601>" }`. Cheap, no auth required, no DB hit.
- The backend should also know its own build SHA — same mechanism.

### 2c. Client-side version check
- On app boot, capture the build SHA the client started with.
- Poll `/api/version` on tab focus (use the `visibilitychange` event — don't poll on a timer, it's wasteful for a B2B app with infrequent deploys). Also check on app boot.
- If server version differs from boot version, surface a non-blocking banner: "A new version is available. [Reload]" Clicking reload calls `window.location.reload()`.
- The banner should be dismissible but reappear on next focus check until the user reloads.
- Don't sign the user out. Don't auto-reload.

### 2d. Minimum-supported-version gate (for breaking changes only)
- The client sends its build SHA as a header on every API request (e.g. `X-Client-Version`).
- The backend has a configurable `MINIMUM_SUPPORTED_CLIENT_VERSION` (env var or config). For most releases this stays the same — it only bumps when we ship a genuinely breaking change.
- If the client version is below the minimum, return `426 Upgrade Required`.
- The client's API layer catches 426 globally and triggers a hard reload prompt (modal, not banner — this one blocks).

### 2e. Tests + verification
- Unit tests for the version-check logic (mismatch detection, focus-triggered re-check, 426 handling).
- Manual verification steps documented: deploy a new version, confirm an open tab from before the deploy sees the banner on focus.

---

## Constraints and preferences

- **Don't add a service worker** if one doesn't already exist. Not worth the complexity here.
- **Don't introduce new runtime dependencies** if a few lines of code will do. The version check should be ~50 lines of client code, not a library.
- **TypeScript throughout**, strict mode if it's already enabled.
- **No localStorage for version state** — boot version lives in memory, server version is fetched. localStorage gets stale in its own special ways and we don't need persistence here.
- Match the existing code style and project structure. If there's an existing pattern for API clients, banners, or polling, use it rather than inventing a new one.
- Keep changes scoped. This is infrastructure plumbing — it shouldn't touch feature code beyond wiring up the banner component somewhere global.

---

## Out of scope (for now)

- Patch notes / changelog UI — that's a follow-up task once this lands.
- Forced sign-outs — explicitly not doing this.
- Service worker introduction.
- Any auth or session changes.

---

## Deliverable for Phase 1

A markdown report covering sections 1–6 above. Be specific with file paths, config snippets, and header values. If you can't determine something without infrastructure access I don't have configured (e.g. CloudFront console), say so explicitly and tell me what you'd need me to check.
