import '@testing-library/jest-dom/vitest';

// jsdom implements no ResizeObserver, and Radix measures with one — a `Switch`
// throws on render without it. It belongs here rather than in each suite: the
// need is a property of the environment, not of any one test.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
