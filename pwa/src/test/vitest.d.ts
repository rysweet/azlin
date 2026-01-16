/**
 * Vitest global types declaration
 *
 * Declares window.open and other browser globals used in tests
 */

declare global {
  const global: typeof globalThis & {
    open: typeof window.open;
    fetch: typeof globalThis.fetch;
  };
}

export {};
