/**
 * VM Wizard - Review Step (Step 6 of 6)
 *
 * Final review and VM creation:
 * - Summary of all configuration choices
 * - Cost estimate (hourly and monthly)
 * - Create button with progress tracking
 * - Error handling and retry logic
 *
 * Philosophy:
 * - Single responsibility: Review and submit
 * - Clear summary with edit links
 * - Transparent cost breakdown
 */

import { useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Stack,
  Divider,
  Button,
  Alert,
  LinearProgress,
  IconButton,
  Chip,
  List,
  ListItem,
  ListItemText,
} from '@mui/material';
import {
  Edit as EditIcon,
  CheckCircle as CheckCircleIcon,
  Computer as ComputerIcon,
  Image as ImageIcon,
  NetworkCheck as NetworkIcon,
  VpnKey as VpnKeyIcon,
  AttachMoney as MoneyIcon,
} from '@mui/icons-material';
import { WizardStepProps, VmCreationRequest, VmCreationProgress } from '../types/VmWizardTypes';
import { useCostCalculation } from '../hooks/useCostCalculation';
import { useVmCreation } from '../hooks/useVmCreation';
import { createLogger } from '../../../utils/logger';

const logger = createLogger('[ReviewStep]');

interface ReviewStepProps extends WizardStepProps<VmCreationRequest> {
  onEditStep: (step: number) => void;
  creationProgress?: VmCreationProgress;
  isSubmitting: boolean;
}

function ReviewStep({
  data,
  errors,
  onEditStep,
  creationProgress,
  isSubmitting,
}: ReviewStepProps) {
  const { calculateCost, getVmSizeDetails } = useCostCalculation();
  const { createVm } = useVmCreation();

  const [creationError, setCreationError] = useState<string>('');

  // Calculate costs
  const vmSizeDetails = data.size ? getVmSizeDetails(data.size.vmSize) : undefined;
  const costEstimate = data.size && data.network
    ? calculateCost(data.size.vmSize, data.network.publicIp)
    : undefined;

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  };

  const handleCreate = async () => {
    try {
      setCreationError('');
      logger.info('Starting VM creation...');

      // Call useVmCreation hook
      await createVm(data as VmCreationRequest);

      logger.info('VM creation completed successfully');
    } catch (err: any) {
      const errorMsg = err.message || 'Failed to create VM';
      setCreationError(errorMsg);
      logger.error('VM creation failed:', errorMsg);
    }
  };

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 1 }}>
        Review & Create
      </Typography>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Review your configuration and create your virtual machine.
      </Typography>

      {/* Basics Section */}
      {data.basics && (
        <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <ComputerIcon color="primary" />
              <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                Basics
              </Typography>
            </Stack>
            <IconButton size="small" onClick={() => onEditStep(0)}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Stack>

          <List dense>
            <ListItem>
              <ListItemText
                primary="VM Name"
                secondary={data.basics.vmName}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Resource Group"
                secondary={data.basics.resourceGroup}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Location"
                secondary={data.basics.location}
              />
            </ListItem>
          </List>
        </Paper>
      )}

      {/* Size Section */}
      {data.size && vmSizeDetails && (
        <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <ComputerIcon color="primary" />
              <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                Size
              </Typography>
            </Stack>
            <IconButton size="small" onClick={() => onEditStep(1)}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Stack>

          <List dense>
            <ListItem>
              <ListItemText
                primary="VM Size"
                secondary={
                  <Stack direction="row" spacing={1} alignItems="center">
                    <span>{data.size.vmSize}</span>
                    {vmSizeDetails.recommended && (
                      <Chip label="Recommended" size="small" color="primary" />
                    )}
                  </Stack>
                }
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Specs"
                secondary={`${vmSizeDetails.vCPUs} vCPU, ${vmSizeDetails.memoryGiB} GiB RAM, ${vmSizeDetails.tempStorageGiB} GiB Storage`}
              />
            </ListItem>
          </List>
        </Paper>
      )}

      {/* Image Section */}
      {data.image && (
        <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <ImageIcon color="primary" />
              <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                Operating System
              </Typography>
            </Stack>
            <IconButton size="small" onClick={() => onEditStep(2)}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Stack>

          <List dense>
            <ListItem>
              <ListItemText
                primary="Publisher"
                secondary={data.image.publisher}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Offer"
                secondary={data.image.offer}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="SKU"
                secondary={data.image.sku}
              />
            </ListItem>
          </List>
        </Paper>
      )}

      {/* Network Section */}
      {data.network && (
        <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <NetworkIcon color="primary" />
              <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                Network
              </Typography>
            </Stack>
            <IconButton size="small" onClick={() => onEditStep(3)}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Stack>

          <List dense>
            <ListItem>
              <ListItemText
                primary="Virtual Network"
                secondary={data.network.vnet}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Subnet"
                secondary={data.network.subnet}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Public IP"
                secondary={data.network.publicIp ? 'Enabled' : 'Disabled'}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Network Security Group"
                secondary={data.network.nsg}
              />
            </ListItem>
          </List>
        </Paper>
      )}

      {/* Authentication Section */}
      {data.auth && (
        <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <VpnKeyIcon color="primary" />
              <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
                Authentication
              </Typography>
            </Stack>
            <IconButton size="small" onClick={() => onEditStep(4)}>
              <EditIcon fontSize="small" />
            </IconButton>
          </Stack>

          <List dense>
            <ListItem>
              <ListItemText
                primary="Username"
                secondary={data.auth.username}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="SSH Key"
                secondary={`${data.auth.sshPublicKey.substring(0, 40)}...`}
              />
            </ListItem>
          </List>
        </Paper>
      )}

      <Divider sx={{ my: 3 }} />

      {/* Cost Estimate */}
      {costEstimate && (
        <Paper elevation={0} sx={{ p: 2, mb: 3, bgcolor: 'primary.50', border: 1, borderColor: 'primary.main' }}>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
            <MoneyIcon color="primary" />
            <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
              Cost Estimate
            </Typography>
          </Stack>

          <List dense>
            <ListItem>
              <ListItemText
                primary="Compute"
                secondary={`${formatCurrency(costEstimate.vmCost)}/hour`}
              />
            </ListItem>
            <ListItem>
              <ListItemText
                primary="Storage (OS Disk)"
                secondary={`${formatCurrency(costEstimate.storageCost)}/month`}
              />
            </ListItem>
            {costEstimate.networkCost > 0 && (
              <ListItem>
                <ListItemText
                  primary="Public IP"
                  secondary={`${formatCurrency(costEstimate.networkCost)}/month`}
                />
              </ListItem>
            )}
          </List>

          <Divider sx={{ my: 1 }} />

          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 2 }}>
            <Typography variant="h6">
              Total
            </Typography>
            <Box sx={{ textAlign: 'right' }}>
              <Typography variant="body2" color="text.secondary">
                {formatCurrency(costEstimate.totalHourly)}/hour
              </Typography>
              <Typography variant="h6">
                ~{formatCurrency(costEstimate.totalMonthly)}/month
              </Typography>
            </Box>
          </Stack>
        </Paper>
      )}

      {/* Creation Progress */}
      {isSubmitting && creationProgress && (
        <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            {creationProgress.message}
          </Typography>
          <LinearProgress
            variant="determinate"
            value={creationProgress.progress}
            sx={{ mb: 1 }}
          />
          <Typography variant="caption" color="text.secondary">
            {creationProgress.progress}% complete
            {creationProgress.estimatedTimeRemaining > 0 && (
              <> • ~{Math.ceil(creationProgress.estimatedTimeRemaining / 60)} minutes remaining</>
            )}
          </Typography>
        </Paper>
      )}

      {/* Errors */}
      {creationError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {creationError}
        </Alert>
      )}

      {errors && errors.length > 0 && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {errors.map((error, i) => (
            <div key={i}>{error}</div>
          ))}
        </Alert>
      )}

      {/* Create Button */}
      <Button
        variant="contained"
        size="large"
        fullWidth
        onClick={handleCreate}
        disabled={isSubmitting}
        startIcon={isSubmitting ? undefined : <CheckCircleIcon />}
      >
        {isSubmitting ? 'Creating VM...' : 'Create Virtual Machine'}
      </Button>

      <Alert severity="info" sx={{ mt: 2 }}>
        <Typography variant="body2">
          VM creation typically takes 3-5 minutes. You'll be redirected to the VM details page when complete.
        </Typography>
      </Alert>
    </Box>
  );
}

export default ReviewStep;
