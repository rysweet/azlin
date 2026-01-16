import { useEffect } from 'react';
import { Box, Typography, List, ListItem, ListItemText, CircularProgress, Chip } from '@mui/material';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { AppDispatch } from '../store/store';
import { fetchVMs, selectAllVMs, selectIsLoading } from '../store/vm-store';

function VMListPage() {
  const dispatch = useDispatch<AppDispatch>();
  const navigate = useNavigate();
  const vms = useSelector(selectAllVMs);
  const loading = useSelector(selectIsLoading);

  useEffect(() => {
    dispatch(fetchVMs(undefined));
  }, [dispatch]);

  if (loading && vms.length === 0) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="h4" gutterBottom>
        Virtual Machines
      </Typography>
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
