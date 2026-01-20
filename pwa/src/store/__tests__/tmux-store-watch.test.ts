/**
 * Unit Tests for Tmux Watch State Management
 *
 * Tests the Redux store actions and reducers for watch mode functionality.
 *
 * Philosophy:
 * - Test the contract, not implementation
 * - Clear test names that explain behavior
 * - Arrange-Act-Assert pattern
 */

import { configureStore } from '@reduxjs/toolkit';
import tmuxReducer, {
  setWatchState,
  setHighlightedLines,
  clearWatchState,
  selectWatchState,
} from '../tmux-store';

describe('Tmux Watch State Management', () => {
  let store: ReturnType<typeof createTestStore>;

  function createTestStore() {
    return configureStore({
      reducer: {
        tmux: tmuxReducer,
      },
    });
  }

  beforeEach(() => {
    store = createTestStore();
  });

  describe('setWatchState', () => {
    it('should initialize watch state with default values', () => {
      const snapshotId = 'rg/vm:session';

      store.dispatch(
        setWatchState({
          snapshotId,
          watchState: {
            isWatching: false,
            intervalSeconds: 10,
            autoScroll: true,
            vibrateOnChange: false,
            highlightedLines: [],
          },
        })
      );

      const state = store.getState();
      const watchState = selectWatchState(state, snapshotId);

      expect(watchState).toEqual({
        isWatching: false,
        intervalSeconds: 10,
        autoScroll: true,
        vibrateOnChange: false,
        highlightedLines: [],
      });
    });

    it('should update existing watch state partially', () => {
      const snapshotId = 'rg/vm:session';

      // Initialize
      store.dispatch(
        setWatchState({
          snapshotId,
          watchState: {
            isWatching: false,
            intervalSeconds: 10,
            autoScroll: true,
            vibrateOnChange: false,
            highlightedLines: [],
          },
        })
      );

      // Update isWatching only
      store.dispatch(
        setWatchState({
          snapshotId,
          watchState: { isWatching: true },
        })
      );

      const state = store.getState();
      const watchState = selectWatchState(state, snapshotId);

      expect(watchState?.isWatching).toBe(true);
      expect(watchState?.intervalSeconds).toBe(10); // Unchanged
    });

    it('should handle multiple snapshot IDs independently', () => {
      const snapshotId1 = 'rg/vm1:session1';
      const snapshotId2 = 'rg/vm2:session2';

      store.dispatch(
        setWatchState({
          snapshotId: snapshotId1,
          watchState: { isWatching: true, intervalSeconds: 5 },
        })
      );

      store.dispatch(
        setWatchState({
          snapshotId: snapshotId2,
          watchState: { isWatching: false, intervalSeconds: 30 },
        })
      );

      const state = store.getState();
      const watchState1 = selectWatchState(state, snapshotId1);
      const watchState2 = selectWatchState(state, snapshotId2);

      expect(watchState1?.isWatching).toBe(true);
      expect(watchState1?.intervalSeconds).toBe(5);
      expect(watchState2?.isWatching).toBe(false);
      expect(watchState2?.intervalSeconds).toBe(30);
    });
  });

  describe('setHighlightedLines', () => {
    it('should update highlighted lines', () => {
      const snapshotId = 'rg/vm:session';

      // Initialize watch state first
      store.dispatch(
        setWatchState({
          snapshotId,
          watchState: { highlightedLines: [] },
        })
      );

      // Set highlighted lines
      const highlights = [
        { lineNumber: 10, type: 'changed' as const },
        { lineNumber: 15, type: 'new' as const },
      ];

      store.dispatch(
        setHighlightedLines({
          snapshotId,
          lines: highlights,
        })
      );

      const state = store.getState();
      const watchState = selectWatchState(state, snapshotId);

      expect(watchState?.highlightedLines).toEqual(highlights);
    });

    it('should replace previous highlights', () => {
      const snapshotId = 'rg/vm:session';

      store.dispatch(
        setWatchState({
          snapshotId,
          watchState: { highlightedLines: [{ lineNumber: 5, type: 'changed' as const }] },
        })
      );

      const newHighlights = [{ lineNumber: 20, type: 'new' as const }];

      store.dispatch(
        setHighlightedLines({
          snapshotId,
          lines: newHighlights,
        })
      );

      const state = store.getState();
      const watchState = selectWatchState(state, snapshotId);

      expect(watchState?.highlightedLines).toEqual(newHighlights);
    });

    it('should handle empty highlights array', () => {
      const snapshotId = 'rg/vm:session';

      store.dispatch(
        setWatchState({
          snapshotId,
          watchState: { highlightedLines: [{ lineNumber: 1, type: 'changed' as const }] },
        })
      );

      store.dispatch(
        setHighlightedLines({
          snapshotId,
          lines: [],
        })
      );

      const state = store.getState();
      const watchState = selectWatchState(state, snapshotId);

      expect(watchState?.highlightedLines).toEqual([]);
    });
  });

  describe('clearWatchState', () => {
    it('should remove watch state for specific snapshot', () => {
      const snapshotId = 'rg/vm:session';

      store.dispatch(
        setWatchState({
          snapshotId,
          watchState: { isWatching: true },
        })
      );

      store.dispatch(clearWatchState(snapshotId));

      const state = store.getState();
      const watchState = selectWatchState(state, snapshotId);

      expect(watchState).toBeUndefined();
    });

    it('should not affect other snapshot watch states', () => {
      const snapshotId1 = 'rg/vm1:session1';
      const snapshotId2 = 'rg/vm2:session2';

      store.dispatch(
        setWatchState({
          snapshotId: snapshotId1,
          watchState: { isWatching: true },
        })
      );

      store.dispatch(
        setWatchState({
          snapshotId: snapshotId2,
          watchState: { isWatching: false },
        })
      );

      store.dispatch(clearWatchState(snapshotId1));

      const state = store.getState();
      const watchState1 = selectWatchState(state, snapshotId1);
      const watchState2 = selectWatchState(state, snapshotId2);

      expect(watchState1).toBeUndefined();
      expect(watchState2?.isWatching).toBe(false);
    });
  });

  describe('selectWatchState', () => {
    it('should return undefined for non-existent snapshot', () => {
      const state = store.getState();
      const watchState = selectWatchState(state, 'non-existent');

      expect(watchState).toBeUndefined();
    });

    it('should return watch state for existing snapshot', () => {
      const snapshotId = 'rg/vm:session';

      store.dispatch(
        setWatchState({
          snapshotId,
          watchState: { isWatching: true, intervalSeconds: 15 },
        })
      );

      const state = store.getState();
      const watchState = selectWatchState(state, snapshotId);

      expect(watchState).toBeDefined();
      expect(watchState?.isWatching).toBe(true);
      expect(watchState?.intervalSeconds).toBe(15);
    });
  });

  describe('Watch Settings Edge Cases', () => {
    it('should handle very short intervals (battery warning territory)', () => {
      const snapshotId = 'rg/vm:session';

      store.dispatch(
        setWatchState({
          snapshotId,
          watchState: { intervalSeconds: 5 },
        })
      );

      const state = store.getState();
      const watchState = selectWatchState(state, snapshotId);

      expect(watchState?.intervalSeconds).toBe(5);
    });

    it('should handle very long intervals', () => {
      const snapshotId = 'rg/vm:session';

      store.dispatch(
        setWatchState({
          snapshotId,
          watchState: { intervalSeconds: 60 },
        })
      );

      const state = store.getState();
      const watchState = selectWatchState(state, snapshotId);

      expect(watchState?.intervalSeconds).toBe(60);
    });

    it('should handle all boolean settings combinations', () => {
      const snapshotId = 'rg/vm:session';

      store.dispatch(
        setWatchState({
          snapshotId,
          watchState: {
            autoScroll: true,
            vibrateOnChange: true,
            isWatching: true,
          },
        })
      );

      const state = store.getState();
      const watchState = selectWatchState(state, snapshotId);

      expect(watchState?.autoScroll).toBe(true);
      expect(watchState?.vibrateOnChange).toBe(true);
      expect(watchState?.isWatching).toBe(true);
    });
  });
});
