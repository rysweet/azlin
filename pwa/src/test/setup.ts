import '@testing-library/jest-dom';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import { server } from './mocks/server';
import 'fake-indexeddb/auto';
import { webcrypto } from 'node:crypto';

// Polyfill Web Crypto API for Node environment
if (!global.crypto) {
  global.crypto = webcrypto as any;
}

// Mock matchMedia for PWA detection tests
global.matchMedia = vi.fn((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addListener: vi.fn(),
  removeListener: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  dispatchEvent: vi.fn(),
})) as any;

// Start MSW server before all tests
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

// Reset handlers after each test
afterEach(() => {
  server.resetHandlers();
  cleanup();
});

// Mock Service Worker registration
global.navigator.serviceWorker = {
  register: vi.fn().mockResolvedValue({}),
  ready: Promise.resolve({} as ServiceWorkerRegistration),
} as any;
