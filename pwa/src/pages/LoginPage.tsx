import { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { Box, Button, Typography, Paper, CircularProgress } from '@mui/material';
import { AppDispatch } from '../store/store';
import {
  initiateDeviceCodeAuth,
  pollForToken,
  selectDeviceCode,
  selectAuthLoading,
  selectAuthError,
} from '../store/auth-store';

function LoginPage() {
  const dispatch = useDispatch<AppDispatch>();
  const deviceCode = useSelector(selectDeviceCode);
  const loading = useSelector(selectAuthLoading);
  const error = useSelector(selectAuthError);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    if (deviceCode && !polling) {
      setPolling(true);
      const intervalId = setInterval(() => {
        dispatch(pollForToken(deviceCode.device_code));
      }, deviceCode.interval * 1000);

      // Clear interval after device code expires
      const timeoutId = setTimeout(() => {
        clearInterval(intervalId);
        setPolling(false);
      }, deviceCode.expires_in * 1000);

      return () => {
        clearInterval(intervalId);
        clearTimeout(timeoutId);
      };
    }
  }, [deviceCode, polling, dispatch]);

  const handleLogin = () => {
    dispatch(initiateDeviceCodeAuth());
  };

  return (
    <Box
      sx={{
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'background.default',
      }}
    >
      <Paper sx={{ p: 4, maxWidth: 400, textAlign: 'center' }}>
        <Typography variant="h4" gutterBottom>
          Azlin Mobile
        </Typography>
        <Typography variant="body2" color="text.secondary" paragraph>
          Manage your Azure VMs from your mobile device
        </Typography>

        {!deviceCode && (
          <Button
            variant="contained"
            fullWidth
            onClick={handleLogin}
            disabled={loading}
          >
            {loading ? <CircularProgress size={24} /> : 'Sign In with Azure'}
          </Button>
        )}

        {deviceCode && (
          <Box>
            <Typography variant="h6" gutterBottom>
              Enter this code:
            </Typography>
            <Typography variant="h3" sx={{ fontFamily: 'monospace', my: 2 }}>
              {deviceCode.user_code}
            </Typography>
            <Typography variant="body2" paragraph>
              Go to{' '}
              <a href={deviceCode.verification_uri} target="_blank" rel="noopener noreferrer">
                {deviceCode.verification_uri}
              </a>
            </Typography>
            <CircularProgress size={32} />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              Waiting for authentication...
            </Typography>
          </Box>
        )}

        {error && (
          <Typography color="error" sx={{ mt: 2 }}>
            {error}
          </Typography>
        )}
      </Paper>
    </Box>
  );
}

export default LoginPage;
