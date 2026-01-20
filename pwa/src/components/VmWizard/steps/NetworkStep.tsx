/**
 * VM Wizard - Network Step (Step 4 of 6)
 *
 * Network configuration:
 * - Virtual Network (VNet) - new or existing
 * - Subnet - new or existing
 * - Public IP - enable/disable
 * - Network Security Group - auto-create with SSH rule
 *
 * Philosophy:
 * - Single responsibility: Network configuration
 * - Smart defaults (create new VNet with default settings)
 * - Clear explanation of networking concepts
 */

import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  TextField,
  FormControl,
  FormControlLabel,
  Switch,
  Alert,
  Paper,
  Divider,
  Stack,
} from '@mui/material';
import {
  Public as PublicIcon,
  Lock as LockIcon,
  Info as InfoIcon,
} from '@mui/icons-material';
import { WizardStepProps, NetworkStepData } from '../types/VmWizardTypes';
// import { createLogger } from '../../../utils/logger';
// const logger = createLogger('[NetworkStep]');

// Default values
const DEFAULT_VNET = 'azlin-vnet';
const DEFAULT_SUBNET = 'default';
const DEFAULT_NSG = 'azlin-nsg';

function NetworkStep({ data, onChange, errors }: WizardStepProps<NetworkStepData>) {
  const [vnet, setVnet] = useState(data?.vnet || DEFAULT_VNET);
  const [subnet, setSubnet] = useState(data?.subnet || DEFAULT_SUBNET);
  const [publicIp, setPublicIp] = useState(data?.publicIp ?? true);
  const [nsg, setNsg] = useState(data?.nsg || DEFAULT_NSG);

  // Update parent when data changes
  useEffect(() => {
    const isValid = vnet.length > 0 && subnet.length > 0 && nsg.length > 0;

    if (isValid) {
      onChange({
        vnet,
        subnet,
        publicIp,
        nsg,
      });
    }
  }, [vnet, subnet, publicIp, nsg, onChange]);

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 1 }}>
        Network Configuration
      </Typography>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Configure the network settings for your VM. Resources will be created automatically if they don't exist.
      </Typography>

      {/* Virtual Network */}
      <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
        <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 'bold' }}>
          Virtual Network (VNet)
        </Typography>

        <TextField
          label="VNet Name"
          fullWidth
          required
          value={vnet}
          onChange={(e) => setVnet(e.target.value)}
          helperText="A virtual network isolates your VMs. Default address space: 10.0.0.0/16"
          placeholder={DEFAULT_VNET}
          sx={{ mb: 2 }}
        />

        <TextField
          label="Subnet Name"
          fullWidth
          required
          value={subnet}
          onChange={(e) => setSubnet(e.target.value)}
          helperText="Subnet within the VNet for this VM. Default address range: 10.0.1.0/24"
          placeholder={DEFAULT_SUBNET}
        />
      </Paper>

      <Divider sx={{ my: 2 }} />

      {/* Public IP */}
      <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
        <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 'bold' }}>
          Public Access
        </Typography>

        <FormControl component="fieldset">
          <FormControlLabel
            control={
              <Switch
                checked={publicIp}
                onChange={(e) => setPublicIp(e.target.checked)}
                color="primary"
              />
            }
            label={
              <Stack direction="row" spacing={1} alignItems="center">
                {publicIp ? (
                  <PublicIcon fontSize="small" color="primary" />
                ) : (
                  <LockIcon fontSize="small" color="action" />
                )}
                <Typography variant="body2">
                  {publicIp ? 'Enable Public IP Address' : 'Private Network Only'}
                </Typography>
              </Stack>
            }
          />
        </FormControl>

        {publicIp ? (
          <Alert severity="info" icon={<InfoIcon />} sx={{ mt: 2 }}>
            <Typography variant="body2">
              Your VM will be accessible from the internet via SSH (port 22).
              A static public IP will be assigned (~$3.65/month).
            </Typography>
          </Alert>
        ) : (
          <Alert severity="warning" sx={{ mt: 2 }}>
            <Typography variant="body2">
              Without a public IP, you'll need to access your VM through a bastion host
              or VPN. This is more secure but requires additional setup.
            </Typography>
          </Alert>
        )}
      </Paper>

      <Divider sx={{ my: 2 }} />

      {/* Network Security Group */}
      <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
        <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 'bold' }}>
          Security
        </Typography>

        <TextField
          label="Network Security Group"
          fullWidth
          required
          value={nsg}
          onChange={(e) => setNsg(e.target.value)}
          helperText="Firewall rules for your VM. SSH (port 22) will be allowed by default."
          placeholder={DEFAULT_NSG}
        />

        <Alert severity="success" icon={<LockIcon />} sx={{ mt: 2 }}>
          <Typography variant="body2">
            <strong>Default Security:</strong> Only SSH (port 22) will be allowed from the internet.
            You can add more rules later in the Azure Portal.
          </Typography>
        </Alert>
      </Paper>

      {/* Validation Errors */}
      {errors && errors.length > 0 && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {errors.map((error, i) => (
            <div key={i}>{error}</div>
          ))}
        </Alert>
      )}

      {/* Info Alert */}
      <Alert severity="info" icon={<InfoIcon />}>
        <Typography variant="body2">
          <strong>What's being created?</strong>
        </Typography>
        <Typography variant="body2" component="div" sx={{ mt: 1 }}>
          • Virtual Network: {vnet} (10.0.0.0/16)
          <br />
          • Subnet: {subnet} (10.0.1.0/24)
          <br />
          • Network Interface: {`<vm-name>-nic`}
          <br />
          {publicIp && (
            <>
              • Public IP: {`<vm-name>-ip`} (Static IPv4)
              <br />
            </>
          )}
          • Network Security Group: {nsg}
        </Typography>
      </Alert>
    </Box>
  );
}

export default NetworkStep;
