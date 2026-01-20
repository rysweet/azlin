/**
 * SizeStep Component Tests
 *
 * Tests for VM size selection step:
 * - Tier selection and filtering
 * - Size selection within tier
 * - Cost calculation display
 * - Step validation
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import SizeStep from '../SizeStep';
import { WizardStepProps, SizeStepData } from '../../types/VmWizardTypes';

// Mock the cost calculation hook
vi.mock('../../hooks/useCostCalculation', () => ({
  useCostCalculation: () => ({
    getVmSizesByTier: (tier: string) => {
      const mockSizes = {
        small: [
          {
            name: 'Standard_B1s',
            vCPUs: 1,
            memoryGiB: 1,
            tempStorageGiB: 4,
            pricePerHour: 0.0104,
            pricePerMonth: 7.59,
            recommended: false,
            tier: 'small',
          },
          {
            name: 'Standard_B2s',
            vCPUs: 2,
            memoryGiB: 4,
            tempStorageGiB: 8,
            pricePerHour: 0.0416,
            pricePerMonth: 30.37,
            recommended: true,
            tier: 'small',
          },
        ],
        medium: [
          {
            name: 'Standard_D2s_v5',
            vCPUs: 2,
            memoryGiB: 8,
            tempStorageGiB: 75,
            pricePerHour: 0.096,
            pricePerMonth: 70.08,
            recommended: true,
            tier: 'medium',
          },
        ],
      };
      return mockSizes[tier as keyof typeof mockSizes] || [];
    },
  }),
}));

// Mock logger
vi.mock('../../../utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}));

describe('SizeStep', () => {
  const mockOnChange = vi.fn();
  const mockOnNext = vi.fn();
  const mockOnPrev = vi.fn();

  const defaultProps: WizardStepProps<SizeStepData> = {
    data: {},
    onChange: mockOnChange,
    onNext: mockOnNext,
    onPrev: mockOnPrev,
    errors: [],
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders tier selection buttons', () => {
    render(<SizeStep {...defaultProps} />);

    expect(screen.getByText(/Small/i)).toBeInTheDocument();
    expect(screen.getByText(/Medium/i)).toBeInTheDocument();
    expect(screen.getByText(/Large/i)).toBeInTheDocument();
    expect(screen.getByText(/XLarge/i)).toBeInTheDocument();
  });

  it('displays VM sizes for selected tier', async () => {
    render(<SizeStep {...defaultProps} />);

    // Medium tier should be selected by default
    await waitFor(() => {
      expect(screen.getByText('Standard_D2s_v5')).toBeInTheDocument();
    });
  });

  it('changes tier when tier button clicked', async () => {
    render(<SizeStep {...defaultProps} />);

    // Click Small tier button
    const smallButton = screen.getByText(/Small/i).closest('button');
    if (smallButton) {
      fireEvent.click(smallButton);
    }

    // Should show small tier sizes
    await waitFor(() => {
      expect(screen.getByText('Standard_B1s')).toBeInTheDocument();
      expect(screen.getByText('Standard_B2s')).toBeInTheDocument();
    });
  });

  it('selects VM size when card clicked', async () => {
    render(<SizeStep {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('Standard_D2s_v5')).toBeInTheDocument();
    });

    // Click the size card
    const sizeCard = screen.getByText('Standard_D2s_v5').closest('[role="button"]');
    if (sizeCard) {
      fireEvent.click(sizeCard);
    }

    // onChange should be called with selected size
    await waitFor(() => {
      expect(mockOnChange).toHaveBeenCalledWith({
        vmSize: 'Standard_D2s_v5',
        tier: 'medium',
      });
    });
  });

  it('displays recommended badge for recommended sizes', async () => {
    render(<SizeStep {...defaultProps} />);

    await waitFor(() => {
      const recommendedChips = screen.getAllByText(/Recommended/i);
      expect(recommendedChips.length).toBeGreaterThan(0);
    });
  });

  it('shows pricing information', async () => {
    render(<SizeStep {...defaultProps} />);

    await waitFor(() => {
      // Should show hourly and monthly prices
      expect(screen.getByText(/\/hour/i)).toBeInTheDocument();
      expect(screen.getByText(/\/month/i)).toBeInTheDocument();
    });
  });

  it('displays VM specs (vCPUs, RAM, storage)', async () => {
    render(<SizeStep {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText(/vCPU/i)).toBeInTheDocument();
      expect(screen.getByText(/GiB RAM/i)).toBeInTheDocument();
      expect(screen.getByText(/Temp Storage/i)).toBeInTheDocument();
    });
  });

  it('auto-selects recommended size when tier changes', async () => {
    render(<SizeStep {...defaultProps} />);

    // Change to small tier
    const smallButton = screen.getByText(/Small/i).closest('button');
    if (smallButton) {
      fireEvent.click(smallButton);
    }

    // Should auto-select Standard_B2s (recommended in small tier)
    await waitFor(() => {
      expect(mockOnChange).toHaveBeenCalledWith(
        expect.objectContaining({
          vmSize: 'Standard_B2s',
          tier: 'small',
        })
      );
    });
  });

  it('renders with pre-selected size from data', () => {
    const propsWithData: WizardStepProps<SizeStepData> = {
      ...defaultProps,
      data: {
        vmSize: 'Standard_D2s_v5',
        tier: 'medium',
      },
    };

    render(<SizeStep {...propsWithData} />);

    // Should show the selected size
    expect(screen.getByText('Standard_D2s_v5')).toBeInTheDocument();
  });

  it('displays validation errors when provided', () => {
    const propsWithErrors: WizardStepProps<SizeStepData> = {
      ...defaultProps,
      errors: ['Please select a VM size'],
    };

    render(<SizeStep {...propsWithErrors} />);

    expect(screen.getByText('Please select a VM size')).toBeInTheDocument();
  });
});
