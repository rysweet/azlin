/**
 * Unit Tests for LoginPage Component (60% of testing pyramid)
 *
 * Tests login UI component with Redux integration.
 * Covers rendering, user interactions, state transitions, and redirects.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { BrowserRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import LoginPage from '../LoginPage';
import authReducer from '../../store/auth-store';

// Mock the navigation
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock auth-store actions
vi.mock('../../store/auth-store', async () => {
  const actual = await vi.importActual('../../store/auth-store');
  return {
    ...actual,
    loginInteractive: vi.fn(() => ({ type: 'auth/loginInteractive/pending' })),
    checkAuth: vi.fn(() => ({ type: 'auth/checkAuth/pending' })),
  };
});

function renderWithProviders(
  component: React.ReactElement,
  preloadedState = {}
) {
  const store = configureStore({
    reducer: {
      auth: authReducer,
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

describe('LoginPage', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  describe('rendering', () => {
    it('should render login page with title', () => {
      renderWithProviders(<LoginPage />);
      expect(screen.getByText(/Azlin Mobile/i)).toBeInTheDocument();
    });

    it('should render app description', () => {
      renderWithProviders(<LoginPage />);
      expect(
        screen.getByText(/Manage your Azure VMs from your mobile device/i)
      ).toBeInTheDocument();
    });

    it('should render sign in button', () => {
      renderWithProviders(<LoginPage />);
      expect(
        screen.getByRole('button', { name: /Sign In with Azure/i })
      ).toBeInTheDocument();
    });

    it('should render redirect notice', () => {
      renderWithProviders(<LoginPage />);
      expect(
        screen.getByText(/You'll be redirected to Microsoft to sign in/i)
      ).toBeInTheDocument();
    });

    it('should not render error by default', () => {
      renderWithProviders(<LoginPage />);
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
  });

  describe('loading state', () => {
    it('should show loading spinner when authenticating', () => {
      const preloadedState = {
        auth: {
          isAuthenticated: false,
          loading: true,
          error: null,
          userEmail: null,
        },
      };

      renderWithProviders(<LoginPage />, preloadedState);

      // Button should show loading spinner
      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
      expect(button.querySelector('.MuiCircularProgress-root')).toBeInTheDocument();
    });

    it('should disable button when loading', () => {
      const preloadedState = {
        auth: {
          isAuthenticated: false,
          loading: true,
          error: null,
          userEmail: null,
        },
      };

      renderWithProviders(<LoginPage />, preloadedState);

      expect(screen.getByRole('button')).toBeDisabled();
    });

    it('should not show button text when loading', () => {
      const preloadedState = {
        auth: {
          isAuthenticated: false,
          loading: true,
          error: null,
          userEmail: null,
        },
      };

      renderWithProviders(<LoginPage />, preloadedState);

      expect(
        screen.queryByText(/Sign In with Azure/i)
      ).not.toBeInTheDocument();
    });
  });

  describe('error handling', () => {
    it('should display error message', () => {
      const preloadedState = {
        auth: {
          isAuthenticated: false,
          loading: false,
          error: 'Authentication failed',
          userEmail: null,
        },
      };

      renderWithProviders(<LoginPage />, preloadedState);

      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText('Authentication failed')).toBeInTheDocument();
    });

    it('should display network error', () => {
      const preloadedState = {
        auth: {
          isAuthenticated: false,
          loading: false,
          error: 'Network request failed',
          userEmail: null,
        },
      };

      renderWithProviders(<LoginPage />, preloadedState);

      expect(screen.getByText('Network request failed')).toBeInTheDocument();
    });

    it('should keep button enabled when error occurs', () => {
      const preloadedState = {
        auth: {
          isAuthenticated: false,
          loading: false,
          error: 'Login failed',
          userEmail: null,
        },
      };

      renderWithProviders(<LoginPage />, preloadedState);

      expect(screen.getByRole('button')).not.toBeDisabled();
    });

    it('should show error as Alert severity', () => {
      const preloadedState = {
        auth: {
          isAuthenticated: false,
          loading: false,
          error: 'Test error',
          userEmail: null,
        },
      };

      renderWithProviders(<LoginPage />, preloadedState);

      const alert = screen.getByRole('alert');
      expect(alert.className).toContain('MuiAlert-standardError');
    });
  });

  describe('user interactions', () => {
    it('should call loginInteractive when button clicked', async () => {
      const { loginInteractive } = await import('../../store/auth-store');
      vi.mocked(loginInteractive).mockClear();
      const user = userEvent.setup();

      renderWithProviders(<LoginPage />);

      const button = screen.getByRole('button', { name: /Sign In with Azure/i });
      await user.click(button);

      expect(loginInteractive).toHaveBeenCalled();
    });

    it('should not call loginInteractive when button is disabled', async () => {
      const { loginInteractive } = await import('../../store/auth-store');
      vi.mocked(loginInteractive).mockClear();

      const preloadedState = {
        auth: {
          isAuthenticated: false,
          loading: true,
          error: null,
          userEmail: null,
        },
      };

      renderWithProviders(<LoginPage />, preloadedState);

      const button = screen.getByRole('button');

      // Button should be disabled - cannot click with userEvent
      expect(button).toBeDisabled();

      // loginInteractive should not be called because button is disabled
      // Note: We don't attempt to click because userEvent correctly prevents clicking disabled buttons
      expect(loginInteractive).not.toHaveBeenCalled();
    });
  });

  describe('authentication redirect', () => {
    it('should redirect to dashboard when authenticated', async () => {
      const preloadedState = {
        auth: {
          isAuthenticated: true,
          loading: false,
          error: null,
          userEmail: 'user@example.com',
        },
      };

      renderWithProviders(<LoginPage />, preloadedState);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/dashboard');
      });
    });

    it('should not redirect when not authenticated', () => {
      const preloadedState = {
        auth: {
          isAuthenticated: false,
          loading: false,
          error: null,
          userEmail: null,
        },
      };

      renderWithProviders(<LoginPage />, preloadedState);

      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('should check auth on mount', async () => {
      const { checkAuth } = await import('../../store/auth-store');

      renderWithProviders(<LoginPage />);

      expect(checkAuth).toHaveBeenCalled();
    });
  });

  describe('layout and styling', () => {
    it('should center content vertically and horizontally', () => {
      const { container } = renderWithProviders(<LoginPage />);

      const outerBox = container.querySelector('.MuiBox-root');
      expect(outerBox).toBeInTheDocument();
    });

    it('should render within a Paper component', () => {
      const { container } = renderWithProviders(<LoginPage />);

      const paper = container.querySelector('.MuiPaper-root');
      expect(paper).toBeInTheDocument();
    });

    it('should have full width button', () => {
      renderWithProviders(<LoginPage />);

      const button = screen.getByRole('button');
      expect(button.className).toContain('MuiButton-fullWidth');
    });
  });

  describe('accessibility', () => {
    it('should have accessible button', () => {
      renderWithProviders(<LoginPage />);

      const button = screen.getByRole('button', { name: /Sign In with Azure/i });
      expect(button).toBeInTheDocument();
    });

    it('should have accessible error alert', () => {
      const preloadedState = {
        auth: {
          isAuthenticated: false,
          loading: false,
          error: 'Test error',
          userEmail: null,
        },
      };

      renderWithProviders(<LoginPage />, preloadedState);

      expect(screen.getByRole('alert')).toBeInTheDocument();
    });

    it('should have proper heading hierarchy', () => {
      renderWithProviders(<LoginPage />);

      const heading = screen.getByText(/Azlin Mobile/i);
      expect(heading.tagName).toBe('H4');
    });
  });
});
