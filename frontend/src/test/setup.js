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
