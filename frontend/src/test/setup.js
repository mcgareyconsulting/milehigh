// Vitest setup — runs once before each test file. Adds jest-dom custom
// matchers (toBeInTheDocument, etc.) to expect().
import '@testing-library/jest-dom/vitest';

// jsdom does not implement ResizeObserver; FloatingBananas (and possibly other
// components) constructs one in useEffect. Stub it.
class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
}
globalThis.ResizeObserver = globalThis.ResizeObserver || ResizeObserverStub;

// Vite's `define` ({ __BUILD_SHA__: ... }) only runs at build time, so unit tests
// running through vitest see a bare reference. Provide a deterministic stub.
globalThis.__BUILD_SHA__ = globalThis.__BUILD_SHA__ || 'test';
