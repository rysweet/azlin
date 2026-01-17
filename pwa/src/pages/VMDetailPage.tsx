import { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Button,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  ListItemButton,
  CircularProgress,
  Alert,
  Chip,
  Divider,
} from '@mui/material';
import { useSelector, useDispatch } from 'react-redux';
import { AppDispatch } from '../store/store';
import { selectVMById, startVM, stopVM } from '../store/vm-store';
import { fetchSessions, selectSessionsByVmId, selectTmuxLoading, selectTmuxError } from '../store/tmux-store';

function VMDetailPage() {
  const { vmId } = useParams<{ vmId: string }>();
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const vm = useSelector((state: any) => selectVMById(state, decodeURIComponent(vmId || '')));

  // Tmux state
  const vmIdKey = vm ? `${vm.resourceGroup}/${vm.name}` : '';
  const sessions = useSelector((state: any) => selectSessionsByVmId(state, vmIdKey));
  const tmuxLoading = useSelector(selectTmuxLoading);
  const tmuxError = useSelector(selectTmuxError);

  // Fetch tmux sessions when VM is running
  useEffect(() => {
    if (vm && vm.powerState === 'running') {
      console.log('🏴‍☠️ Fetching tmux sessions for', vm.name);
      dispatch(fetchSessions({ resourceGroup: vm.resourceGroup, vmName: vm.name }));
    }
  }, [dispatch, vm]);

  if (!vm) {
    return (
      <Box sx={{ p: 2 }}>
        <Alert severity="error">VM not found</Alert>
      </Box>
    );
  }

  const handleStart = () => {
    dispatch(startVM({ resourceGroup: vm.resourceGroup, vmName: vm.name }));
  };

  const handleStop = () => {
    dispatch(stopVM({ resourceGroup: vm.resourceGroup, vmName: vm.name, deallocate: true }));
  };

  const handleSessionClick = (sessionName: string) => {
    const encodedVmId = encodeURIComponent(`${vm.resourceGroup}/${vm.name}`);
    navigate(`/tmux/${encodedVmId}/${encodeURIComponent(sessionName)}`);
  };

  const isRunning = vm.powerState === 'running';

  return (
    <Box sx={{ p: 2 }}>
      {/* VM Header */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <Typography variant="h4" sx={{ flexGrow: 1 }}>
          {vm.name}
        </Typography>
        <Chip
          label={vm.powerState}
          color={isRunning ? 'success' : 'default'}
          size="medium"
        />
      </Box>

      {/* VM Details Card */}
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>VM Details</Typography>
          <Typography>Size: {vm.size}</Typography>
          <Typography>Location: {vm.location}</Typography>
          <Typography>OS: {vm.osType}</Typography>
          <Typography>Resource Group: {vm.resourceGroup}</Typography>
          {vm.privateIP && <Typography>Private IP: {vm.privateIP}</Typography>}
        </CardContent>
      </Card>

      {/* VM Actions */}
      <Box sx={{ mb: 3 }}>
        <Button
          variant="contained"
          color="success"
          onClick={handleStart}
          disabled={isRunning}
          sx={{ mr: 1 }}
        >
          Start
        </Button>
        <Button
          variant="outlined"
          color="error"
          onClick={handleStop}
          disabled={!isRunning}
        >
          Stop & Deallocate
        </Button>
      </Box>

      <Divider sx={{ my: 2 }} />

      {/* Tmux Sessions Section */}
      <Typography variant="h5" gutterBottom>
        Tmux Sessions
      </Typography>

      {!isRunning && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Start the VM to view and interact with tmux sessions
        </Alert>
      )}

      {isRunning && tmuxLoading && (
        <Box sx={{ display: 'flex', alignItems: 'center', p: 2 }}>
          <CircularProgress size={24} sx={{ mr: 2 }} />
          <Typography>Loading tmux sessions...</Typography>
        </Box>
      )}

      {isRunning && tmuxError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {tmuxError}
        </Alert>
      )}

      {isRunning && !tmuxLoading && sessions.length === 0 && !tmuxError && (
        <Alert severity="info">
          No tmux sessions found on this VM. SSH in and run "tmux new -s mysession" to create one.
        </Alert>
      )}

      {isRunning && sessions.length > 0 && (
        <Card>
          <List>
            {sessions.map((session, index) => (
              <ListItem key={session.name} disablePadding divider={index < sessions.length - 1}>
                <ListItemButton onClick={() => handleSessionClick(session.name)}>
                  <ListItemText
                    primary={session.name}
                    secondary={`${session.windowCount} window(s) - Created: ${session.created ? new Date(session.created).toLocaleString() : 'Unknown'}`}
                  />
                  <Chip label="View" size="small" color="primary" />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
        </Card>
      )}

      {isRunning && (
        <Button
          variant="text"
          onClick={() => dispatch(fetchSessions({ resourceGroup: vm.resourceGroup, vmName: vm.name }))}
          sx={{ mt: 2 }}
          disabled={tmuxLoading}
        >
          Refresh Sessions
        </Button>
      )}
    </Box>
  );
}

export default VMDetailPage;
