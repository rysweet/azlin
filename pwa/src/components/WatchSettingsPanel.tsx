/**
 * WatchSettingsPanel Component
 *
 * Settings panel for configuring watch mode (interval, auto-scroll, notifications).
 *
 * Philosophy:
 * - Single responsibility: Watch mode settings UI
 * - Self-contained with clear props interface
 * - Zero-BS: Real settings with real state management
 */

import { Box, FormControl, FormControlLabel, FormLabel, Radio, RadioGroup, Switch, Paper } from '@mui/material';

export interface WatchSettings {
  intervalSeconds: number;
  autoScroll: boolean;
  vibrateOnChange: boolean;
}

export interface WatchSettingsPanelProps {
  settings: WatchSettings;
  onSettingsChange: (settings: WatchSettings) => void;
}

const INTERVAL_OPTIONS = [
  { value: 5, label: '5 seconds (High battery usage)' },
  { value: 10, label: '10 seconds (Recommended)' },
  { value: 30, label: '30 seconds' },
  { value: 60, label: '60 seconds (Battery saver)' },
];

export function WatchSettingsPanel({ settings, onSettingsChange }: WatchSettingsPanelProps) {
  const handleIntervalChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onSettingsChange({
      ...settings,
      intervalSeconds: parseInt(event.target.value, 10),
    });
  };

  const handleAutoScrollChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onSettingsChange({
      ...settings,
      autoScroll: event.target.checked,
    });
  };

  const handleVibrateChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    onSettingsChange({
      ...settings,
      vibrateOnChange: event.target.checked,
    });
  };

  return (
    <Paper sx={{ p: 2, mb: 2 }}>
      <FormControl component="fieldset" fullWidth>
        <FormLabel component="legend" sx={{ mb: 1, fontWeight: 'bold' }}>
          Watch Mode Settings
        </FormLabel>

        <Box sx={{ mb: 2 }}>
          <FormLabel component="legend" sx={{ mb: 1, fontSize: '0.875rem' }}>
            Refresh Interval
          </FormLabel>
          <RadioGroup
            value={settings.intervalSeconds}
            onChange={handleIntervalChange}
          >
            {INTERVAL_OPTIONS.map(option => (
              <FormControlLabel
                key={option.value}
                value={option.value}
                control={<Radio />}
                label={option.label}
              />
            ))}
          </RadioGroup>
        </Box>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <FormControlLabel
            control={
              <Switch
                checked={settings.autoScroll}
                onChange={handleAutoScrollChange}
              />
            }
            label="Auto-scroll to bottom on changes"
          />

          <FormControlLabel
            control={
              <Switch
                checked={settings.vibrateOnChange}
                onChange={handleVibrateChange}
              />
            }
            label="Vibrate on content changes"
          />
        </Box>
      </FormControl>
    </Paper>
  );
}

export default WatchSettingsPanel;
