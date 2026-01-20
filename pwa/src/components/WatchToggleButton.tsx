/**
 * WatchToggleButton Component
 *
 * Toggle button for enabling/disabling watch mode in tmux sessions.
 *
 * Philosophy:
 * - Single responsibility: Watch mode toggle UI
 * - Self-contained with clear props interface
 * - Zero-BS: Real button with real state management
 */

import { Button } from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import VisibilityOffIcon from '@mui/icons-material/VisibilityOff';

export interface WatchToggleButtonProps {
  isWatching: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export function WatchToggleButton({ isWatching, onToggle, disabled = false }: WatchToggleButtonProps) {
  return (
    <Button
      variant={isWatching ? 'contained' : 'outlined'}
      onClick={onToggle}
      disabled={disabled}
      startIcon={isWatching ? <VisibilityIcon /> : <VisibilityOffIcon />}
      color={isWatching ? 'success' : 'primary'}
      sx={{ minWidth: 120 }}
    >
      {isWatching ? 'Watching' : 'Watch'}
    </Button>
  );
}

export default WatchToggleButton;
