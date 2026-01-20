/**
 * VM Wizard Container
 *
 * Main wizard orchestration component that manages:
 * - Step navigation and progress
 * - State management and persistence
 * - Step validation
 * - VM creation flow
 *
 * Philosophy:
 * - Single responsibility: Wizard orchestration
 * - Delegates rendering to step components
 * - Manages global wizard state
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Paper,
  Stepper,
  Step,
  StepLabel,
  Button,
  Stack,
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  ArrowForward as ArrowForwardIcon,
} from '@mui/icons-material';
import { useVmWizardState } from './hooks/useVmWizardState';
import BasicsStep from './steps/BasicsStep';
import SizeStep from './steps/SizeStep';
import ImageStep from './steps/ImageStep';
import NetworkStep from './steps/NetworkStep';
import AuthStep from './steps/AuthStep';
import ReviewStep from './steps/ReviewStep';
import { createLogger } from '../../utils/logger';

const logger = createLogger('[VmWizardContainer]');

const STEP_LABELS = [
  'Basics',
  'Size',
  'Image',
  'Network',
  'Authentication',
  'Review & Create',
];

function VmWizardContainer() {
  const navigate = useNavigate();
  const { state, actions, helpers } = useVmWizardState();

  // Redirect to VM details page when creation completes
  useEffect(() => {
    if (state.vmId) {
      logger.info('VM created successfully, redirecting to details page');
      navigate(`/vms/${state.vmId}`);
    }
  }, [state.vmId, navigate]);

  const handleNext = () => {
    // Validate current step before proceeding
    const currentStepKey = helpers.currentStepKey as keyof typeof state.data;
    const currentStepData = currentStepKey ? state.data[currentStepKey] : null;

    if (!currentStepData) {
      actions.setValidation(state.currentStep, ['Please complete this step before continuing']);
      return;
    }

    actions.nextStep();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handlePrev = () => {
    actions.prevStep();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleStepClick = (step: number) => {
    // Allow jumping to any step (wizard is flexible)
    actions.goToStep(step);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const renderCurrentStep = () => {
    const stepIndex = state.currentStep;
    const stepKey = helpers.currentStepKey as keyof typeof state.data;
    const stepData = stepKey ? state.data[stepKey] || {} : {};
    const stepErrors = stepKey ? state.validation[stepKey] || [] : [];

    const commonProps = {
      data: stepData as any,
      onChange: (data: any) => actions.updateStep(stepIndex, data),
      onNext: handleNext,
      onPrev: handlePrev,
      errors: stepErrors,
      isFirst: stepIndex === 0,
      isLast: stepIndex === helpers.totalSteps - 1,
    };

    switch (stepIndex) {
      case 0:
        return <BasicsStep {...commonProps} />;
      case 1:
        return <SizeStep {...commonProps} />;
      case 2:
        return <ImageStep {...commonProps} />;
      case 3:
        return <NetworkStep {...commonProps} />;
      case 4:
        return <AuthStep {...commonProps} />;
      case 5:
        return (
          <ReviewStep
            {...commonProps}
            data={state.data as any}
            onEditStep={handleStepClick}
            creationProgress={state.creationProgress}
            isSubmitting={state.isSubmitting}
          />
        );
      default:
        return null;
    }
  };

  const isLastStep = state.currentStep === helpers.totalSteps - 1;
  const canProceed = helpers.currentStepKey
    ? !!state.data[helpers.currentStepKey as keyof typeof state.data]
    : false;

  return (
    <Container maxWidth="md" sx={{ py: 4 }}>
      <Paper elevation={2} sx={{ p: 4 }}>
        {/* Stepper */}
        <Stepper activeStep={state.currentStep} sx={{ mb: 4 }}>
          {STEP_LABELS.map((label, index) => (
            <Step key={label} completed={index < state.currentStep}>
              <StepLabel
                sx={{ cursor: 'pointer' }}
                onClick={() => handleStepClick(index)}
              >
                {label}
              </StepLabel>
            </Step>
          ))}
        </Stepper>

        {/* Current Step Content */}
        <Box sx={{ mb: 4 }}>
          {renderCurrentStep()}
        </Box>

        {/* Navigation Buttons */}
        {!isLastStep && (
          <Stack
            direction="row"
            spacing={2}
            justifyContent="space-between"
            sx={{ mt: 4 }}
          >
            <Button
              variant="outlined"
              onClick={handlePrev}
              disabled={!helpers.canGoPrev || state.isSubmitting}
              startIcon={<ArrowBackIcon />}
            >
              Back
            </Button>

            <Button
              variant="contained"
              onClick={handleNext}
              disabled={!canProceed || !helpers.canGoNext || state.isSubmitting}
              endIcon={<ArrowForwardIcon />}
            >
              Next
            </Button>
          </Stack>
        )}

        {/* Review step handles its own buttons */}
        {isLastStep && (
          <Stack
            direction="row"
            spacing={2}
            justifyContent="flex-start"
            sx={{ mt: 4 }}
          >
            <Button
              variant="outlined"
              onClick={handlePrev}
              disabled={state.isSubmitting}
              startIcon={<ArrowBackIcon />}
            >
              Back
            </Button>
          </Stack>
        )}
      </Paper>
    </Container>
  );
}

export default VmWizardContainer;
