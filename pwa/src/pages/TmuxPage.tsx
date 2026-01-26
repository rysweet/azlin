import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Typography, TextField, Button, CircularProgress, IconButton, Collapse } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import SettingsIcon from '@mui/icons-material/Settings';
import { useDispatch, useSelector } from 'react-redux';
import { AppDispatch } from '../store/store';
import {
  captureSnapshot,
  sendKeys,
  selectSnapshotById,
  selectTmuxLoading,
  selectTmuxError,
  selectPollingProgress,
  selectWatchState,
  setWatchState,
  setHighlightedLines,
  clearWatchState,
} from '../store/tmux-store';
import { TmuxApi, TmuxWatcher } from '../tmux/tmux-api';
import { AzureClient } from '../api/azure-client';
import { WatchToggleButton } from '../components/WatchToggleButton';
import { WatchStatusBanner } from '../components/WatchStatusBanner';
import { WatchSettingsPanel, WatchSettings } from '../components/WatchSettingsPanel';
import { TmuxTerminalDisplay } from '../components/TmuxTerminalDisplay';

function TmuxPage() {
  const { vmId, sessionName } = useParams<{ vmId: string; sessionName: string }>();
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const [command, setCommand] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const watcherRef = useRef<TmuxWatcher | null>(null);
  const tmuxApiRef = useRef<TmuxApi | null>(null);

  // Decode vmId since it comes from URL params
  const decodedVmId = decodeURIComponent(vmId || '');
  const [resourceGroup, vmName] = decodedVmId.split('/');
  const decodedSessionName = decodeURIComponent(sessionName || '');
  const snapshotId = `${decodedVmId}:${decodedSessionName}`;

  const snapshot = useSelector((state: any) => selectSnapshotById(state, snapshotId));
  const loading = useSelector(selectTmuxLoading);
  const error = useSelector(selectTmuxError);
  const pollingProgress = useSelector(selectPollingProgress);
  const watchState = useSelector((state: any) => selectWatchState(state, snapshotId));

  // Initialize tmux API
  useEffect(() => {
    const subscriptionId = import.meta.env.VITE_AZURE_SUBSCRIPTION_ID;
    const azureClient = new AzureClient(subscriptionId);
    tmuxApiRef.current = new TmuxApi(azureClient);
  }, []);

  // Initialize watch state
  useEffect(() => {
    if (!watchState) {
      dispatch(
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
    }
  }, [dispatch, snapshotId, watchState]);

  // Initial snapshot capture
  useEffect(() => {
    if (resourceGroup && vmName && sessionName) {
      dispatch(captureSnapshot({ resourceGroup, vmName, sessionName: decodedSessionName }));
    }
  }, [dispatch, resourceGroup, vmName, sessionName, decodedSessionName]);

  // Cleanup watcher on unmount
  useEffect(() => {
    return () => {
      if (watcherRef.current) {
        watcherRef.current.stop();
      }
      dispatch(clearWatchState(snapshotId));
    };
  }, [dispatch, snapshotId]);

  const handleSendKeys = () => {
    if (command && resourceGroup && vmName && sessionName) {
      dispatch(sendKeys({ resourceGroup, vmName, sessionName: decodedSessionName, keys: command }));
      setCommand('');
      // Refresh snapshot after sending keys
      setTimeout(() => {
        dispatch(captureSnapshot({ resourceGroup, vmName, sessionName: decodedSessionName }));
      }, 1000);
    }
  };

  const handleRefresh = () => {
    if (resourceGroup && vmName && sessionName) {
      dispatch(captureSnapshot({ resourceGroup, vmName, sessionName: decodedSessionName }));
    }
  };

  const handleToggleWatch = () => {
    if (!watchState || !tmuxApiRef.current) return;

    const isWatching = watchState.isWatching;

    if (isWatching) {
      // Stop watching
      if (watcherRef.current) {
        watcherRef.current.stop();
        watcherRef.current = null;
      }
      dispatch(
        setWatchState({
          snapshotId,
          watchState: { ...watchState, isWatching: false },
        })
      );
    } else {
      // Start watching
      const watcher = tmuxApiRef.current.watchSession(
        resourceGroup,
        vmName,
        decodedSessionName,
        (diff) => {
          // Update highlighted lines
          const highlights = diff.changedLines.map((change: any) => ({
            lineNumber: change.lineNumber,
            type: change.oldContent === '' ? ('new' as const) : ('changed' as const),
          }));

          dispatch(setHighlightedLines({ snapshotId, lines: highlights }));

          // Vibrate if enabled
          if (watchState.vibrateOnChange && navigator.vibrate) {
            navigator.vibrate(200);
          }

          // Clear highlights after 3 seconds
          setTimeout(() => {
            dispatch(setHighlightedLines({ snapshotId, lines: [] }));
          }, 3000);
        },
        watchState.intervalSeconds * 1000,
        (error) => {
          console.error('Watch error:', error);
          // Stop watching on error
          if (watcherRef.current) {
            watcherRef.current.stop();
            watcherRef.current = null;
          }
          dispatch(
            setWatchState({
              snapshotId,
              watchState: { ...watchState, isWatching: false },
            })
          );
        }
      );

      watcher.start();
      watcherRef.current = watcher;

      dispatch(
        setWatchState({
          snapshotId,
          watchState: { ...watchState, isWatching: true },
        })
      );
    }
  };

  const handleSettingsChange = (newSettings: WatchSettings) => {
    const wasWatching = watchState?.isWatching;

    // Update settings in store
    dispatch(
      setWatchState({
        snapshotId,
        watchState: {
          ...watchState,
          ...newSettings,
          isWatching: watchState?.isWatching || false,
        },
      })
    );

    // If watching and interval changed, restart watcher
    if (wasWatching && newSettings.intervalSeconds !== watchState?.intervalSeconds) {
      if (watcherRef.current) {
        watcherRef.current.stop();
      }

      // Restart with new interval after state updates
      setTimeout(() => {
        handleToggleWatch(); // Stop
        setTimeout(() => handleToggleWatch(), 100); // Start with new interval
      }, 100);
    }
  };

  const showBatteryWarning = watchState?.isWatching && watchState?.intervalSeconds < 10;

  return (
    <Box sx={{ p: 2 }}>
      {/* Header with back button */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <IconButton onClick={() => navigate(-1)} sx={{ mr: 1 }}>
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="h5" sx={{ flexGrow: 1 }}>
          Tmux: {decodedSessionName}
        </Typography>

        <IconButton onClick={() => setShowSettings(!showSettings)} sx={{ mr: 1 }}>
          <SettingsIcon />
        </IconButton>

        <WatchToggleButton
          isWatching={watchState?.isWatching || false}
          onToggle={handleToggleWatch}
          disabled={loading}
        />

        <Button variant="outlined" onClick={handleRefresh} disabled={loading} sx={{ ml: 1 }}>
          Refresh
        </Button>
      </Box>

      {/* Watch status banner */}
      {watchState?.isWatching && (
        <WatchStatusBanner
          intervalSeconds={watchState.intervalSeconds}
          showBatteryWarning={showBatteryWarning}
        />
      )}

      {/* Settings panel (collapsible) */}
      <Collapse in={showSettings}>
        {watchState && (
          <WatchSettingsPanel
            settings={{
              intervalSeconds: watchState.intervalSeconds,
              autoScroll: watchState.autoScroll,
              vibrateOnChange: watchState.vibrateOnChange,
            }}
            onSettingsChange={handleSettingsChange}
          />
        )}
      </Collapse>

      {/* Loading indicator with polling progress */}
      {loading && (
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', p: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <CircularProgress size={24} sx={{ mr: 2 }} />
            <Typography>
              {pollingProgress ? pollingProgress.message : 'Capturing tmux snapshot...'}
            </Typography>
          </Box>
          {pollingProgress && (
            <Typography variant="caption" color="text.secondary">
              Attempt {pollingProgress.attempt} of {pollingProgress.maxAttempts}
            </Typography>
          )}
        </Box>
      )}

      {/* Error display */}
      {error && (
        <Typography color="error" sx={{ mb: 2 }}>
          {error}
        </Typography>
      )}

      {/* Terminal display with highlighting */}
      <TmuxTerminalDisplay
        lines={snapshot?.paneContent || []}
        highlights={watchState?.highlightedLines || []}
        autoScroll={watchState?.autoScroll}
        loading={loading}
      />

      {/* Command input */}
      <Box sx={{ mt: 2, display: 'flex' }}>
        <TextField
          fullWidth
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder="Enter command..."
          onKeyPress={(e) => e.key === 'Enter' && handleSendKeys()}
          disabled={loading}
        />
        <Button variant="contained" onClick={handleSendKeys} sx={{ ml: 1 }} disabled={loading || !command}>
          Send
        </Button>
      </Box>
    </Box>
  );
}

export default TmuxPage;
