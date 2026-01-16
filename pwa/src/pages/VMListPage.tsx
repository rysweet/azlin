import { useEffect } from 'react';
import { Box, Typography, List, ListItem, ListItemText, CircularProgress, Chip, Alert } from '@mui/material';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { AppDispatch } from '../store/store';
import { fetchVMs, selectAllVMs, selectIsLoading, selectError } from '../store/vm-store';

function VMListPage() {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const vms = useSelector(selectAllVMs);
  const loading = useSelector(selectIsLoading);
  const error = useSelector(selectError);

  useEffect(() => {
    console.log('🏴‍☠️ VMListPage: Fetching VMs...');
    dispatch(fetchVMs(undefined));
  }, [dispatch]);

  useEffect(() => {
    console.log('🏴‍☠️ VMListPage state:', { vmsCount: vms.length, loading, error });
  }, [vms, loading, error]);

  if (loading && vms.length === 0) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
        <Typography sx={{ ml: 2 }}>Loading VMs...</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="h4" gutterBottom>
        Virtual Machines
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {!loading && vms.length === 0 && !error && (
        <Alert severity="info">
          No VMs found. Create one with "azlin new" or check your subscription/resource group.
        </Alert>
      )}

      <List>
        {vms.map((vm) => (
          <ListItem
            key={vm.id}
            button
            onClick={() => navigate(`/vms/${encodeURIComponent(vm.id)}`)}
          >
            <ListItemText
              primary={vm.name}
              secondary={`${vm.size} - ${vm.location}`}
            />
            <Chip
              label={vm.powerState}
              color={vm.powerState === 'running' ? 'success' : 'default'}
              size="small"
            />
          </ListItem>
        ))}
      </List>
    </Box>
  );
}

export default VMListPage;
