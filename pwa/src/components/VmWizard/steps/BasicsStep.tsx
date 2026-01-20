/**
 * VM Wizard - Basics Step (Step 1 of 6)
 *
 * Collects basic VM information:
 * - VM Name
 * - Resource Group
 * - Azure Region
 *
 * Philosophy:
 * - Single responsibility: Basic VM configuration
 * - Real-time validation with clear feedback
 * - Smart defaults to minimize user input
 */

import { useState, useEffect } from 'react';
import {
  Box,
  TextField,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  FormHelperText,
  CircularProgress,
} from '@mui/material';
import { WizardStepProps, BasicsStepData, AzureLocation } from '../types/VmWizardTypes';
import { validateVmName, sanitizeVmName } from '../../../utils/vm-name-validator';
import { AzureClient } from '../../../api/azure-client';
import { createLogger } from '../../../utils/logger';

const logger = createLogger('[BasicsStep]');

// Default values
const DEFAULT_RESOURCE_GROUP = import.meta.env.VITE_AZURE_RESOURCE_GROUP?.trim() || 'azlin-vms';
const DEFAULT_LOCATION = 'eastus';

function BasicsStep({ data, onChange, errors }: WizardStepProps<BasicsStepData>) {
  const [vmName, setVmName] = useState(data?.vmName || '');
  const [resourceGroup, setResourceGroup] = useState(data?.resourceGroup || DEFAULT_RESOURCE_GROUP);
  const [location, setLocation] = useState(data?.location || DEFAULT_LOCATION);

  const [vmNameErrors, setVmNameErrors] = useState<string[]>([]);
  const [locations, setLocations] = useState<AzureLocation[]>([]);
  const [loadingLocations, setLoadingLocations] = useState(false);

  // Load Azure locations on mount
  useEffect(() => {
    const loadLocations = async () => {
      try {
        setLoadingLocations(true);
        const subscriptionId = import.meta.env.VITE_AZURE_SUBSCRIPTION_ID?.trim() || '';
        const client = new AzureClient(subscriptionId);
        const locs = await client.listLocations();

        // Sort by display name
        locs.sort((a, b) => a.displayName.localeCompare(b.displayName));

        setLocations(locs);
        logger.debug('Loaded locations:', locs.length);
      } catch (err: any) {
        logger.error('Failed to load locations:', err);
        // Use fallback common locations
        setLocations([
          { name: 'eastus', displayName: 'East US', regionalDisplayName: '(US) East US' },
          { name: 'westus', displayName: 'West US', regionalDisplayName: '(US) West US' },
          { name: 'centralus', displayName: 'Central US', regionalDisplayName: '(US) Central US' },
          { name: 'westeurope', displayName: 'West Europe', regionalDisplayName: '(Europe) West Europe' },
          { name: 'northeurope', displayName: 'North Europe', regionalDisplayName: '(Europe) North Europe' },
        ]);
      } finally {
        setLoadingLocations(false);
      }
    };

    loadLocations();
  }, []);

  // Validate VM name on change
  useEffect(() => {
    if (!vmName) {
      setVmNameErrors([]);
      return;
    }

    const result = validateVmName(vmName);
    setVmNameErrors(result.errors);
  }, [vmName]);

  // Update parent when data changes
  useEffect(() => {
    const isValid = vmName.length > 0 && resourceGroup.length > 0 && location.length > 0 && vmNameErrors.length === 0;

    if (isValid) {
      onChange({
        vmName,
        resourceGroup,
        location,
      });
    }
  }, [vmName, resourceGroup, location, vmNameErrors, onChange]);

  // Handle VM name change with auto-sanitization
  const handleVmNameChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    let value = event.target.value;

    // Auto-sanitize: convert to lowercase, replace spaces with hyphens
    if (value) {
      value = value.toLowerCase().replace(/\s+/g, '-');
    }

    setVmName(value);
  };

  // Handle VM name blur (cleanup on focus loss)
  const handleVmNameBlur = () => {
    if (vmName) {
      const sanitized = sanitizeVmName(vmName);
      if (sanitized !== vmName) {
        setVmName(sanitized);
      }
    }
  };

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 2 }}>
        Basic Configuration
      </Typography>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Provide the basic information for your new virtual machine.
      </Typography>

      {/* VM Name */}
      <TextField
        label="VM Name"
        fullWidth
        required
        value={vmName}
        onChange={handleVmNameChange}
        onBlur={handleVmNameBlur}
        error={vmNameErrors.length > 0}
        helperText={
          vmNameErrors.length > 0
            ? vmNameErrors[0]
            : 'Lowercase letters, numbers, and hyphens only. Must start with a letter.'
        }
        placeholder="my-ubuntu-vm"
        sx={{ mb: 2 }}
        autoFocus
      />

      {/* Resource Group */}
      <TextField
        label="Resource Group"
        fullWidth
        required
        value={resourceGroup}
        onChange={(e) => setResourceGroup(e.target.value)}
        helperText="Azure resource group for the VM. Will be created if it doesn't exist."
        placeholder={DEFAULT_RESOURCE_GROUP}
        sx={{ mb: 2 }}
      />

      {/* Location */}
      <FormControl fullWidth required sx={{ mb: 2 }}>
        <InputLabel>Azure Region</InputLabel>
        <Select
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          label="Azure Region"
          disabled={loadingLocations}
        >
          {loadingLocations ? (
            <MenuItem value={location}>
              <CircularProgress size={20} sx={{ mr: 1 }} />
              Loading regions...
            </MenuItem>
          ) : locations.length === 0 ? (
            <MenuItem value={DEFAULT_LOCATION}>East US</MenuItem>
          ) : (
            locations.map((loc) => (
              <MenuItem key={loc.name} value={loc.name}>
                {loc.regionalDisplayName || loc.displayName}
              </MenuItem>
            ))
          )}
        </Select>
        <FormHelperText>
          Choose a region close to you for better performance
        </FormHelperText>
      </FormControl>

      {/* Validation Errors from Parent */}
      {errors && errors.length > 0 && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {errors.map((error, i) => (
            <div key={i}>{error}</div>
          ))}
        </Alert>
      )}

      {/* Info Alert */}
      <Alert severity="info" sx={{ mt: 2 }}>
        <Typography variant="body2">
          <strong>Tip:</strong> VM names cannot be changed after creation. Choose wisely!
        </Typography>
      </Alert>
    </Box>
  );
}

export default BasicsStep;
