/**
 * VM Wizard State Management Hook
 *
 * Custom React hook managing wizard state using useReducer pattern.
 * Handles step navigation, validation, draft persistence, and creation flow.
 *
 * Philosophy:
 * - Single source of truth for wizard state
 * - Predictable state transitions via reducer
 * - Draft persistence to localStorage
 * - Zero-BS: All state changes are explicit and traceable
 */

import { useReducer, useEffect, useCallback } from 'react';
import {
  VmWizardState,
  VmWizardAction,
  VmCreationRequest,
  VmCreationProgress,
} from '../types/VmWizardTypes';
import { createLogger } from '../../../utils/logger';

const logger = createLogger('[useVmWizardState]');

const DRAFT_STORAGE_KEY = 'azlin-vm-wizard-draft';
const TOTAL_STEPS = 6;

// ============================================================================
// Initial State
// ============================================================================

const initialState: VmWizardState = {
  currentStep: 0,
  data: {},
  validation: {},
  isDirty: false,
  isSubmitting: false,
};

// ============================================================================
// State Reducer
// ============================================================================

function vmWizardReducer(state: VmWizardState, action: VmWizardAction): VmWizardState {
  logger.debug('Reducer action:', action.type, action);

  switch (action.type) {
    case 'NEXT_STEP':
      if (state.currentStep < TOTAL_STEPS - 1) {
        return {
          ...state,
          currentStep: state.currentStep + 1,
        };
      }
      return state;

    case 'PREV_STEP':
      if (state.currentStep > 0) {
        return {
          ...state,
          currentStep: state.currentStep - 1,
        };
      }
      return state;

    case 'GO_TO_STEP':
      if (action.step >= 0 && action.step < TOTAL_STEPS) {
        return {
          ...state,
          currentStep: action.step,
        };
      }
      return state;

    case 'UPDATE_STEP': {
      const stepKey = getStepKey(action.step);
      if (!stepKey) return state;

      return {
        ...state,
        data: {
          ...state.data,
          [stepKey]: action.data,
        },
        isDirty: true,
      };
    }

    case 'SET_VALIDATION': {
      const stepKey = getStepKey(action.step);
      if (!stepKey) return state;

      return {
        ...state,
        validation: {
          ...state.validation,
          [stepKey]: action.errors,
        },
      };
    }

    case 'START_CREATION':
      return {
        ...state,
        isSubmitting: true,
        error: undefined,
      };

    case 'UPDATE_PROGRESS':
      return {
        ...state,
        creationProgress: action.progress,
      };

    case 'CREATION_COMPLETE':
      return {
        ...state,
        isSubmitting: false,
        vmId: action.vmId,
        creationProgress: undefined,
      };

    case 'CREATION_ERROR':
      return {
        ...state,
        isSubmitting: false,
        error: action.error,
        creationProgress: undefined,
      };

    case 'RESET':
      return initialState;

    case 'RESTORE_DRAFT':
      logger.debug('Restoring draft:', action.state);
      return {
        ...action.state,
        isSubmitting: false,  // Never restore submitting state
        creationProgress: undefined,
      };

    default:
      return state;
  }
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Map step index to data key
 */
function getStepKey(step: number): keyof VmCreationRequest | null {
  const keys: Array<keyof VmCreationRequest> = ['basics', 'size', 'image', 'network', 'auth'];
  return keys[step] || null;
}

/**
 * Check if wizard data is complete (all steps filled)
 */
function isWizardComplete(data: Partial<VmCreationRequest>): data is VmCreationRequest {
  return !!(
    data.basics &&
    data.size &&
    data.image &&
    data.network &&
    data.auth
  );
}

// ============================================================================
// Draft Persistence Functions
// ============================================================================

function saveDraft(state: VmWizardState): void {
  try {
    // Only save if wizard has some data
    if (!state.isDirty) return;

    const draftToSave = {
      currentStep: state.currentStep,
      data: state.data,
      isDirty: state.isDirty,
    };

    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draftToSave));
    logger.debug('Draft saved to localStorage');
  } catch (error) {
    logger.error('Failed to save draft:', error);
  }
}

function restoreDraft(): VmWizardState | null {
  try {
    const draftJson = localStorage.getItem(DRAFT_STORAGE_KEY);
    if (!draftJson) return null;

    const draft = JSON.parse(draftJson);
    logger.debug('Draft restored from localStorage:', draft);

    return {
      ...initialState,
      ...draft,
    };
  } catch (error) {
    logger.error('Failed to restore draft:', error);
    return null;
  }
}

function clearDraft(): void {
  try {
    localStorage.removeItem(DRAFT_STORAGE_KEY);
    logger.debug('Draft cleared from localStorage');
  } catch (error) {
    logger.error('Failed to clear draft:', error);
  }
}

// ============================================================================
// Hook Export
// ============================================================================

export interface UseVmWizardStateReturn {
  state: VmWizardState;
  actions: {
    nextStep: () => void;
    prevStep: () => void;
    goToStep: (step: number) => void;
    updateStep: (step: number, data: unknown) => void;
    setValidation: (step: number, errors: string[]) => void;
    startCreation: () => void;
    updateProgress: (progress: VmCreationProgress) => void;
    completeCreation: (vmId: string) => void;
    errorCreation: (error: string) => void;
    reset: () => void;
  };
  helpers: {
    isComplete: boolean;
    canGoNext: boolean;
    canGoPrev: boolean;
    currentStepKey: string | null;
    totalSteps: number;
  };
}

export function useVmWizardState(): UseVmWizardStateReturn {
  // Initialize reducer with draft if available
  const [state, dispatch] = useReducer(vmWizardReducer, initialState, (initial) => {
    const draft = restoreDraft();
    return draft || initial;
  });

  // Save draft whenever state changes
  useEffect(() => {
    saveDraft(state);
  }, [state]);

  // Clear draft on successful creation
  useEffect(() => {
    if (state.vmId) {
      clearDraft();
    }
  }, [state.vmId]);

  // Actions
  const nextStep = useCallback(() => {
    dispatch({ type: 'NEXT_STEP' });
  }, []);

  const prevStep = useCallback(() => {
    dispatch({ type: 'PREV_STEP' });
  }, []);

  const goToStep = useCallback((step: number) => {
    dispatch({ type: 'GO_TO_STEP', step });
  }, []);

  const updateStep = useCallback((step: number, data: unknown) => {
    dispatch({ type: 'UPDATE_STEP', step, data });
  }, []);

  const setValidation = useCallback((step: number, errors: string[]) => {
    dispatch({ type: 'SET_VALIDATION', step, errors });
  }, []);

  const startCreation = useCallback(() => {
    dispatch({ type: 'START_CREATION' });
  }, []);

  const updateProgress = useCallback((progress: VmCreationProgress) => {
    dispatch({ type: 'UPDATE_PROGRESS', progress });
  }, []);

  const completeCreation = useCallback((vmId: string) => {
    dispatch({ type: 'CREATION_COMPLETE', vmId });
  }, []);

  const errorCreation = useCallback((error: string) => {
    dispatch({ type: 'CREATION_ERROR', error });
  }, []);

  const reset = useCallback(() => {
    clearDraft();
    dispatch({ type: 'RESET' });
  }, []);

  // Helpers
  const isComplete = isWizardComplete(state.data);
  const canGoNext = state.currentStep < TOTAL_STEPS - 1;
  const canGoPrev = state.currentStep > 0;
  const currentStepKey = getStepKey(state.currentStep);

  return {
    state,
    actions: {
      nextStep,
      prevStep,
      goToStep,
      updateStep,
      setValidation,
      startCreation,
      updateProgress,
      completeCreation,
      errorCreation,
      reset,
    },
    helpers: {
      isComplete,
      canGoNext,
      canGoPrev,
      currentStepKey,
      totalSteps: TOTAL_STEPS,
    },
  };
}

export default useVmWizardState;
