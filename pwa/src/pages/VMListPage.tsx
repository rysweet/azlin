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

    // DIAGNOSTIC: First check what subscriptions the token can see
    const testSubscriptionAccess = async () => {
      try {
        const token = await new (await import('../auth/token-storage')).TokenStorage().getAccessToken();
        console.log('🏴‍☠️ Token length:', token?.length || 0);

        // Test: List subscriptions to see what we have access to
        const subsResponse = await fetch(
          'https://management.azure.com/subscriptions?api-version=2022-12-01',
          { headers: { 'Authorization': `Bearer ${token}` } }
        );

        const subsData = await subsResponse.json();
        console.log('🏴‍☠️ Subscriptions API response:', subsData);

        if (subsData.value) {
          const subs = subsData.value.map(s => ({
            id: s.subscriptionId,
            name: s.displayName
          }));
          console.log('🏴‍☠️ Subscriptions accessible:', subs);

          // Log each subscription explicitly as STRING
          subsData.value.forEach((s, i) => {
            console.log(`🏴‍☠️ Subscription ${i + 1}: ID="${s.subscriptionId}" Name="${s.displayName}" State="${s.state}"`);
          });

          // Compare with env var
          const envSubId = import.meta.env.VITE_AZURE_SUBSCRIPTION_ID;
          const tokenSubId = subsData.value[0].subscriptionId;

          console.log(`🏴‍☠️ TOKEN has access to subscription: "${tokenSubId}"`);
          console.log(`🏴‍☠️ .env configured subscription:     "${envSubId}"`);
          console.log(`🏴‍☠️ IDs match: ${tokenSubId === envSubId}`);

          if (tokenSubId !== envSubId) {
            console.error(`🏴‍☠️ ❌ MISMATCH! Token subscription differs from .env!`);
            console.error(`🏴‍☠️    Update .env to use: ${tokenSubId}`);
          }
        }
      } catch (e) {
        console.error('🏴‍☠️ Subscription test failed:', e);
      }
    };

    testSubscriptionAccess();

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
