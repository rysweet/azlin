/**
 * VM Wizard - Image Step (Step 3 of 6)
 *
 * Operating system image selection:
 * - Ubuntu 22.04 LTS (Jammy Jellyfish) - RECOMMENDED
 * - Ubuntu 24.04 LTS (Noble Numbat) - Latest LTS
 * - Debian 12 (Bookworm) - Stable
 * - RHEL 9 - Enterprise
 *
 * Philosophy:
 * - Single responsibility: OS image selection
 * - Curated list of production-ready images
 * - Smart defaults (Ubuntu 22.04 LTS)
 */

import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  CardActionArea,
  Grid,
  Chip,
  Alert,
  Stack,
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  Info as InfoIcon,
} from '@mui/icons-material';
import { WizardStepProps, ImageStepData, OsPreset } from '../types/VmWizardTypes';
import { createLogger } from '../../../utils/logger';

const logger = createLogger('[ImageStep]');

// ============================================================================
// OS Image Presets
// ============================================================================

const OS_PRESETS: OsPreset[] = [
  {
    id: 'ubuntu-2204',
    name: 'Ubuntu 22.04 LTS',
    publisher: 'Canonical',
    offer: '0001-com-ubuntu-server-jammy',
    sku: '22_04-lts-gen2',
    version: 'latest',
    description: 'Long-term support until 2027. Most popular choice for cloud VMs. Great balance of stability and modern features.',
  },
  {
    id: 'ubuntu-2404',
    name: 'Ubuntu 24.04 LTS',
    publisher: 'Canonical',
    offer: '0001-com-ubuntu-server-noble',
    sku: '24_04-lts-gen2',
    version: 'latest',
    description: 'Latest LTS release with support until 2029. Cutting-edge features and latest packages.',
  },
  {
    id: 'debian-12',
    name: 'Debian 12 (Bookworm)',
    publisher: 'Debian',
    offer: 'debian-12',
    sku: '12-gen2',
    version: 'latest',
    description: 'Rock-solid stability. Perfect for servers requiring minimal changes and maximum reliability.',
  },
  {
    id: 'rhel-9',
    name: 'Red Hat Enterprise Linux 9',
    publisher: 'RedHat',
    offer: 'RHEL',
    sku: '9-lvm-gen2',
    version: 'latest',
    description: 'Enterprise Linux with commercial support. Ideal for business-critical workloads and compliance requirements.',
  },
];

const RECOMMENDED_IMAGE_ID = 'ubuntu-2204';

function ImageStep({ data, onChange, errors }: WizardStepProps<ImageStepData>) {
  const [selectedImageId, setSelectedImageId] = useState<string>('');

  // Initialize from existing data or default
  useEffect(() => {
    if (data && data.publisher) {
      // Find matching preset from data
      const preset = OS_PRESETS.find(
        p => p.publisher === data.publisher && p.offer === data.offer && p.sku === data.sku
      );
      if (preset) {
        setSelectedImageId(preset.id);
      }
    } else {
      // Default to recommended
      setSelectedImageId(RECOMMENDED_IMAGE_ID);
    }
  }, [data]);

  // Update parent when selection changes
  useEffect(() => {
    if (selectedImageId) {
      const preset = OS_PRESETS.find(p => p.id === selectedImageId);
      if (preset) {
        onChange({
          publisher: preset.publisher,
          offer: preset.offer,
          sku: preset.sku,
          version: preset.version,
        });
      }
    }
  }, [selectedImageId, onChange]);

  const handleImageSelect = (preset: OsPreset) => {
    setSelectedImageId(preset.id);
    logger.debug('Selected image:', preset.name);
  };

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 1 }}>
        Choose Operating System
      </Typography>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Select the operating system for your virtual machine. All images are Gen2 VMs with latest security updates.
      </Typography>

      {/* OS Grid */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        {OS_PRESETS.map((preset) => {
          const isSelected = selectedImageId === preset.id;
          const isRecommended = preset.id === RECOMMENDED_IMAGE_ID;

          return (
            <Grid item xs={12} key={preset.id}>
              <Card
                variant="outlined"
                sx={{
                  position: 'relative',
                  borderColor: isSelected ? 'primary.main' : 'divider',
                  borderWidth: isSelected ? 2 : 1,
                  backgroundColor: isSelected ? 'action.selected' : 'background.paper',
                }}
              >
                <CardActionArea onClick={() => handleImageSelect(preset)}>
                  <CardContent>
                    {/* Header with Name and Badges */}
                    <Stack
                      direction="row"
                      spacing={1}
                      alignItems="center"
                      sx={{ mb: 1 }}
                    >
                      <Typography variant="h6" component="div">
                        {preset.name}
                      </Typography>

                      {isRecommended && (
                        <Chip
                          label="Recommended"
                          size="small"
                          color="primary"
                          icon={<CheckCircleIcon />}
                        />
                      )}

                      {preset.id.includes('rhel') && (
                        <Chip
                          label="Enterprise"
                          size="small"
                          color="secondary"
                        />
                      )}
                    </Stack>

                    {/* Description */}
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ mb: 1.5 }}
                    >
                      {preset.description}
                    </Typography>

                    {/* Technical Details */}
                    <Stack
                      direction="row"
                      spacing={1}
                      sx={{ opacity: 0.7 }}
                    >
                      <Typography variant="caption" color="text.secondary">
                        Publisher: {preset.publisher}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        •
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        SKU: {preset.sku}
                      </Typography>
                    </Stack>

                    {/* Selected Indicator */}
                    {isSelected && (
                      <CheckCircleIcon
                        color="primary"
                        sx={{
                          position: 'absolute',
                          top: 16,
                          right: 16,
                        }}
                      />
                    )}
                  </CardContent>
                </CardActionArea>
              </Card>
            </Grid>
          );
        })}
      </Grid>

      {/* Validation Errors */}
      {errors && errors.length > 0 && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {errors.map((error, i) => (
            <div key={i}>{error}</div>
          ))}
        </Alert>
      )}

      {/* Info Alerts */}
      <Alert severity="info" icon={<InfoIcon />}>
        <Typography variant="body2">
          <strong>About LTS (Long-Term Support):</strong> LTS versions receive security updates
          and bug fixes for 5 years, making them ideal for production servers.
        </Typography>
      </Alert>

      <Alert severity="warning" sx={{ mt: 2 }}>
        <Typography variant="body2">
          <strong>Note:</strong> You cannot change the OS after creation. Choose carefully!
        </Typography>
      </Alert>
    </Box>
  );
}

export default ImageStep;
