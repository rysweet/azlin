/**
 * Unit Tests for VMListPage Component (60% of testing pyramid)
 *
 * Tests VM list UI component with Redux integration.
 * Covers rendering, VM cards, power states, refresh, and navigation.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { BrowserRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import VMListPage from '../VMListPage';
import vmReducer from '../../store/vm-store';

// Mock the navigation
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock vm-store actions
vi.mock('../../store/vm-store', async () => {
  const actual = await vi.importActual('../../store/vm-store');
  return {
    ...actual,
    fetchVMs: vi.fn(() => ({ type: 'vms/fetchVMs/pending' })),
  };
});

// Mock logger
vi.mock('../../utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}));

function renderWithProviders(
  component: React.ReactElement,
  preloadedState = {}
) {
  const store = configureStore({
    reducer: {
      vms: vmReducer,
    },
    preloadedState,
  });

  return {
    ...render(
      <Provider store={store}>
        <BrowserRouter>{component}</BrowserRouter>
      </Provider>
    ),
    store,
  };
}

const mockVMs = [
  {
    id: '/subscriptions/xxx/resourceGroups/rg-test/providers/Microsoft.Compute/virtualMachines/vm-1',
    name: 'test-vm-1',
    resourceGroup: 'rg-test',
    powerState: 'running',
    size: 'Standard_D2s_v3',
    location: 'eastus',
    privateIP: '10.0.0.4',
    osType: 'Linux',
  },
  {
    id: '/subscriptions/xxx/resourceGroups/rg-test/providers/Microsoft.Compute/virtualMachines/vm-2',
    name: 'test-vm-2',
    resourceGroup: 'rg-test',
    powerState: 'deallocated',
    size: 'Standard_E8as_v5',
    location: 'westus2',
    privateIP: '10.0.0.5',
    osType: 'Linux',
  },
  {
    id: '/subscriptions/xxx/resourceGroups/rg-test/providers/Microsoft.Compute/virtualMachines/vm-3',
    name: 'test-vm-3',
    resourceGroup: 'rg-test',
    powerState: 'starting',
    size: 'Standard_B2s',
    location: 'centralus',
    privateIP: null,
    osType: 'Windows',
  },
];

describe('VMListPage', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  describe('rendering', () => {
    it('should render page title', () => {
      renderWithProviders(<VMListPage />);
      expect(screen.getByText('Azure VMs')).toBeInTheDocument();
    });

    it('should render refresh button', () => {
      renderWithProviders(<VMListPage />);
      expect(
        screen.getByRole('button', { name: /Refresh/i })
      ).toBeInTheDocument();
    });

    it('should fetch VMs on mount', async () => {
      const { fetchVMs } = await import('../../store/vm-store');

      renderWithProviders(<VMListPage />);

      expect(fetchVMs).toHaveBeenCalled();
    });
  });

  describe('loading state', () => {
    it('should show loading spinner when fetching VMs', () => {
      const preloadedState = {
        vms: {
          items: [],
          loading: true,
          error: null,
          lastSync: null,
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByRole('progressbar')).toBeInTheDocument();
      expect(screen.getByText('Loading VMs...')).toBeInTheDocument();
    });

    it('should not show loading spinner when VMs already loaded', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: true,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      // Should show VMs, not loading spinner
      expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
      expect(screen.getByText('test-vm-1')).toBeInTheDocument();
    });

    it('should show "Refreshing..." on button when loading', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: true,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(
        screen.getByRole('button', { name: /Refreshing/i })
      ).toBeInTheDocument();
    });

    it('should disable refresh button when loading', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: true,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByRole('button', { name: /Refreshing/i })).toBeDisabled();
    });
  });

  describe('VM list display', () => {
    it('should render all VMs', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByText('test-vm-1')).toBeInTheDocument();
      expect(screen.getByText('test-vm-2')).toBeInTheDocument();
      expect(screen.getByText('test-vm-3')).toBeInTheDocument();
    });

    it('should display VM specs', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByText('2 vCPU, 8GB')).toBeInTheDocument(); // Standard_D2s_v3
      expect(screen.getByText('8 vCPU, 64GB')).toBeInTheDocument(); // Standard_E8as_v5
    });

    it('should display tier labels for azlin tier VMs', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByText('S')).toBeInTheDocument(); // Small tier
      expect(screen.getByText('M')).toBeInTheDocument(); // Medium tier
    });

    it('should display VM locations', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByText('eastus')).toBeInTheDocument();
      expect(screen.getByText('westus2')).toBeInTheDocument();
      expect(screen.getByText('centralus')).toBeInTheDocument();
    });

    it('should display private IPs when available', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByText('10.0.0.4')).toBeInTheDocument();
      expect(screen.getByText('10.0.0.5')).toBeInTheDocument();
    });

    it('should display OS type', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getAllByText('Linux')).toHaveLength(2);
      expect(screen.getByText('Windows')).toBeInTheDocument();
    });

    it('should show empty state when no VMs', () => {
      const preloadedState = {
        vms: {
          items: [],
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(
        screen.getByText(
          /No VMs found. Create one with "azlin new" or check your subscription/
        )
      ).toBeInTheDocument();
    });
  });

  describe('power state display', () => {
    it('should show running state with success color', () => {
      const preloadedState = {
        vms: {
          items: [mockVMs[0]], // running VM
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      const chip = screen.getByText('running').closest('.MuiChip-root');
      expect(chip?.className).toContain('MuiChip-colorSuccess');
    });

    it('should show deallocated state with error color', () => {
      const preloadedState = {
        vms: {
          items: [mockVMs[1]], // deallocated VM
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      const chip = screen.getByText('deallocated').closest('.MuiChip-root');
      expect(chip?.className).toContain('MuiChip-colorError');
    });

    it('should show starting state with warning color', () => {
      const preloadedState = {
        vms: {
          items: [mockVMs[2]], // starting VM
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      const chip = screen.getByText('starting').closest('.MuiChip-root');
      expect(chip?.className).toContain('MuiChip-colorWarning');
    });

    it('should show stopped state with error color', () => {
      const stoppedVM = { ...mockVMs[0], powerState: 'stopped' };
      const preloadedState = {
        vms: {
          items: [stoppedVM],
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      const chip = screen.getByText('stopped').closest('.MuiChip-root');
      expect(chip?.className).toContain('MuiChip-colorError');
    });
  });

  describe('error handling', () => {
    it('should display error message', () => {
      const preloadedState = {
        vms: {
          items: [],
          loading: false,
          error: 'Failed to fetch VMs',
          lastSync: null,
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Failed to fetch VMs')).toBeInTheDocument();
    });

    it('should show VMs even with error', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: false,
          error: 'Refresh failed',
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('test-vm-1')).toBeInTheDocument();
    });
  });

  describe('user interactions', () => {
    it('should call fetchVMs when refresh button clicked', async () => {
      const { fetchVMs } = await import('../../store/vm-store');
      const user = userEvent.setup();

      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      // Get initial call count
      const initialCalls = vi.mocked(fetchVMs).mock.calls.length;

      const refreshButton = screen.getByRole('button', { name: /Refresh/i });
      await user.click(refreshButton);

      // Should have one more call after clicking refresh
      expect(vi.mocked(fetchVMs).mock.calls.length).toBeGreaterThan(initialCalls);
    });

    it('should navigate to VM details when card clicked', async () => {
      const user = userEvent.setup();

      const preloadedState = {
        vms: {
          items: [mockVMs[0]],
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      const card = screen.getByText('test-vm-1').closest('.MuiCardActionArea-root');
      expect(card).toBeInTheDocument();

      await user.click(card!);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith(
          `/vms/${encodeURIComponent(mockVMs[0].id)}`
        );
      });
    });
  });

  describe('summary statistics', () => {
    it('should show total VM count', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByText(/Total: 3 VMs/i)).toBeInTheDocument();
    });

    it('should show running VM count', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByText(/1 running/i)).toBeInTheDocument();
    });

    it('should handle singular VM text', () => {
      const preloadedState = {
        vms: {
          items: [mockVMs[0]],
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByText(/Total: 1 VM[^s]/i)).toBeInTheDocument();
    });

    it('should show zero running when all deallocated', () => {
      const deallocatedVMs = mockVMs.map(vm => ({
        ...vm,
        powerState: 'deallocated',
      }));

      const preloadedState = {
        vms: {
          items: deallocatedVMs,
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByText(/0 running/i)).toBeInTheDocument();
    });
  });

  describe('layout and styling', () => {
    it('should render VMs in grid layout', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      const { container } = renderWithProviders(<VMListPage />, preloadedState);

      const grid = container.querySelector('.MuiGrid-container');
      expect(grid).toBeInTheDocument();
    });

    it('should render each VM in a card', () => {
      const preloadedState = {
        vms: {
          items: mockVMs,
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      const { container } = renderWithProviders(<VMListPage />, preloadedState);

      const cards = container.querySelectorAll('.MuiCard-root');
      expect(cards).toHaveLength(3);
    });
  });

  describe('accessibility', () => {
    it('should have accessible refresh button', () => {
      renderWithProviders(<VMListPage />);

      const button = screen.getByRole('button', { name: /Refresh/i });
      expect(button).toBeInTheDocument();
    });

    it('should have accessible alert for errors', () => {
      const preloadedState = {
        vms: {
          items: [],
          loading: false,
          error: 'Test error',
          lastSync: null,
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it('should have clickable VM cards', () => {
      const preloadedState = {
        vms: {
          items: [mockVMs[0]],
          loading: false,
          error: null,
          lastSync: Date.now(),
        },
      };

      renderWithProviders(<VMListPage />, preloadedState);

      const actionArea = screen.getByText('test-vm-1').closest('.MuiCardActionArea-root');
      expect(actionArea).toBeInTheDocument();
    });
  });
});
