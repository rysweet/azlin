import { useEffect } from 'react';
import {
  Box,
  Typography,
  CircularProgress,
  Chip,
  Alert,
  Card,
  CardContent,
  CardActionArea,
  Grid,
  Button,
  Fab,
} from '@mui/material';
import { Add as AddIcon } from '@mui/icons-material';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { AppDispatch } from '../store/store';
import { fetchVMs, selectAllVMs, selectIsLoading, selectError } from '../store/vm-store';
import { formatVMSpecs, getVMTier } from '../utils/vm-size-specs';
import { createLogger } from '../utils/logger';

const logger = createLogger('[VMListPage]');

function VMListPage() {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const vms = useSelector(selectAllVMs);
  const loading = useSelector(selectIsLoading);
  const error = useSelector(selectError);

  useEffect(() => {
    logger.debug('Fetching VMs...');
    dispatch(fetchVMs(undefined));
  }, [dispatch]);

  useEffect(() => {
    logger.debug('VMListPage state:', { vmsCount: vms.length, loading, error });
    logger.debug('VMs:', vms);
  }, [vms, loading, error]);

  const handleRefresh = () => {
    dispatch(fetchVMs(undefined));
  };

  const getPowerStateColor = (powerState: string): 'success' | 'error' | 'warning' | 'default' => {
    switch (powerState.toLowerCase()) {
      case 'running':
        return 'success';
      case 'deallocated':
      case 'stopped':
        return 'error';
      case 'starting':
      case 'stopping':
        return 'warning';
      default:
        return 'default';
    }
  };

  if (loading && vms.length === 0) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', p: 4, minHeight: '50vh' }}>
        <CircularProgress />
        <Typography sx={{ ml: 2 }}>Loading VMs...</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <Typography variant="h5" sx={{ flexGrow: 1 }}>
          Azure VMs
        </Typography>
        <Button
          variant="outlined"
          onClick={handleRefresh}
          disabled={loading}
          size="small"
        >
          {loading ? 'Refreshing...' : 'Refresh'}
        </Button>
      </Box>

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

      <Grid container spacing={2}>
        {vms.map((vm) => (
          <Grid item xs={12} key={vm.id}>
            <Card>
              <CardActionArea onClick={() => navigate(`/vms/${encodeURIComponent(vm.id)}`)}>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                    <Box sx={{ flexGrow: 1 }}>
                      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, flexWrap: 'wrap' }}>
                        <Typography variant="h6" component="div">
                          {vm.name}
                        </Typography>
                        {getVMTier(vm.size) && (
                          <Chip
                            label={getVMTier(vm.size)?.toUpperCase()}
                            size="small"
                            variant="outlined"
                            sx={{ height: 20, fontSize: '0.7rem' }}
                          />
                        )}
                      </Box>
                      <Typography variant="body2" color="text.primary" sx={{ fontWeight: 500 }}>
                        {formatVMSpecs(vm.size)}
                      </Typography>
                      <Box sx={{ mt: 0.5, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                        <Typography variant="body2" color="text.secondary">
                          {vm.location}
                        </Typography>
                        {vm.privateIP && (
                          <Typography variant="body2" color="text.secondary">
                            {vm.privateIP}
                          </Typography>
                        )}
                        <Typography variant="body2" color="text.secondary">
                          {vm.osType}
                        </Typography>
                      </Box>
                    </Box>
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
                      <Chip
                        label={vm.powerState}
                        color={getPowerStateColor(vm.powerState)}
                        size="small"
                      />
                    </Box>
                  </Box>
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Box sx={{ mt: 2 }}>
        <Typography variant="body2" color="text.secondary">
          Total: {vms.length} VM{vms.length !== 1 ? 's' : ''} | {vms.filter(v => v.powerState?.toLowerCase() === 'running').length} running
        </Typography>
      </Box>

      {/* Floating Action Button for Create VM */}
      <Fab
        color="primary"
        aria-label="create vm"
        onClick={() => navigate('/vms/create')}
        sx={{
          position: 'fixed',
          bottom: 16,
          right: 16,
        }}
      >
        <AddIcon />
      </Fab>
    </Box>
  );
}

export default VMListPage;
