import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Box, Typography, Paper, TextField, Button, CircularProgress, IconButton } from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { useDispatch, useSelector } from 'react-redux';
import { AppDispatch } from '../store/store';
import { captureSnapshot, sendKeys, selectSnapshotById, selectTmuxLoading, selectTmuxError, selectPollingProgress } from '../store/tmux-store';

function TmuxPage() {
  const { vmId, sessionName } = useParams<{ vmId: string; sessionName: string }>();
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const [command, setCommand] = useState('');

  // Decode vmId since it comes from URL params
  const decodedVmId = decodeURIComponent(vmId || '');
  const [resourceGroup, vmName] = decodedVmId.split('/');
  const snapshotId = `${decodedVmId}:${decodeURIComponent(sessionName || '')}`;
  const snapshot = useSelector((state: any) => selectSnapshotById(state, snapshotId));
  const loading = useSelector(selectTmuxLoading);
  const error = useSelector(selectTmuxError);
  const pollingProgress = useSelector(selectPollingProgress);

  useEffect(() => {
    if (resourceGroup && vmName && sessionName) {
      dispatch(captureSnapshot({ resourceGroup, vmName, sessionName: decodeURIComponent(sessionName) }));
    }
  }, [dispatch, resourceGroup, vmName, sessionName]);

  const handleSendKeys = () => {
    if (command && resourceGroup && vmName && sessionName) {
      dispatch(sendKeys({ resourceGroup, vmName, sessionName: decodeURIComponent(sessionName), keys: command }));
      setCommand('');
      // Refresh snapshot after sending keys
      setTimeout(() => {
        dispatch(captureSnapshot({ resourceGroup, vmName, sessionName: decodeURIComponent(sessionName) }));
      }, 1000);
    }
  };

  const handleRefresh = () => {
    if (resourceGroup && vmName && sessionName) {
      dispatch(captureSnapshot({ resourceGroup, vmName, sessionName: decodeURIComponent(sessionName) }));
    }
  };

  return (
    <Box sx={{ p: 2 }}>
      {/* Header with back button */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <IconButton onClick={() => navigate(-1)} sx={{ mr: 1 }}>
          <ArrowBackIcon />
        </IconButton>
        <Typography variant="h5" sx={{ flexGrow: 1 }}>
          Tmux: {decodeURIComponent(sessionName || '')}
        </Typography>
        <Button variant="outlined" onClick={handleRefresh} disabled={loading}>
          Refresh
        </Button>
      </Box>

      {/* Loading indicator with polling progress */}
      {loading && (
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', p: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <CircularProgress size={24} sx={{ mr: 2 }} />
            <Typography>
              {pollingProgress
                ? pollingProgress.message
                : 'Capturing tmux snapshot...'}
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

      {/* Terminal display */}
      <Paper
        sx={{
          p: 2,
          bgcolor: 'black',
          color: '#00ff00',
          fontFamily: 'monospace',
          fontSize: '14px',
          minHeight: 400,
          maxHeight: '60vh',
          overflow: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
        }}
      >
        {snapshot?.paneContent && snapshot.paneContent.length > 0 ? (
          snapshot.paneContent.map((line, idx) => (
            <div key={idx}>{line || ' '}</div>
          ))
        ) : (
          !loading && <Typography color="grey.500">No content captured yet. Click Refresh to load.</Typography>
        )}
      </Paper>

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
