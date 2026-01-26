/**
 * WatchStatusBanner Component
 *
 * Status banner for watch mode showing refresh interval and battery warning.
 *
 * Philosophy:
 * - Single responsibility: Watch mode status display
 * - Self-contained with clear props interface
 * - Zero-BS: Real status display with real warnings
 */

import { Alert, Box, Chip } from '@mui/material';
import BatteryAlertIcon from '@mui/icons-material/BatteryAlert';

export interface WatchStatusBannerProps {
  intervalSeconds: number;
  showBatteryWarning?: boolean;
}

export function WatchStatusBanner({ intervalSeconds, showBatteryWarning = false }: WatchStatusBannerProps) {
  return (
    <Alert
      severity={showBatteryWarning ? 'warning' : 'info'}
      icon={showBatteryWarning ? <BatteryAlertIcon /> : undefined}
      sx={{ mb: 2 }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
        <span>Watch mode active</span>
        <Chip
          label={`Refreshing every ${intervalSeconds}s`}
          size="small"
          color="primary"
          variant="outlined"
        />
        {showBatteryWarning && (
          <span style={{ fontSize: '0.875rem' }}>
            (High battery usage - consider increasing interval)
          </span>
        )}
      </Box>
    </Alert>
  );
}

export default WatchStatusBanner;
