/**
 * VM Wizard - Size Step (Step 2 of 6)
 *
 * VM size selection with tier-based categorization:
 * - Small: Development/testing (< $50/month)
 * - Medium: Production workloads ($50-150/month)
 * - Large: High-performance apps ($150-400/month)
 * - XLarge: Enterprise workloads (> $400/month)
 *
 * Philosophy:
 * - Single responsibility: VM size selection
 * - Real-time cost preview
 * - Smart recommendations based on use case
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
  ToggleButtonGroup,
  ToggleButton,
  Stack,
} from '@mui/material';
import {
  Memory as MemoryIcon,
  Storage as StorageIcon,
  Speed as SpeedIcon,
  CheckCircle as CheckCircleIcon,
} from '@mui/icons-material';
import { WizardStepProps, SizeStepData, VmSizeOption } from '../types/VmWizardTypes';
import { useCostCalculation } from '../hooks/useCostCalculation';
import { createLogger } from '../../../utils/logger';

const logger = createLogger('[SizeStep]');

type Tier = 'small' | 'medium' | 'large' | 'xlarge';

const TIER_INFO = {
  small: {
    label: 'Small',
    description: 'Development & Testing',
    color: '#4caf50' as const,
  },
  medium: {
    label: 'Medium',
    description: 'Production Workloads',
    color: '#2196f3' as const,
  },
  large: {
    label: 'Large',
    description: 'High-Performance Apps',
    color: '#ff9800' as const,
  },
  xlarge: {
    label: 'XLarge',
    description: 'Enterprise Workloads',
    color: '#f44336' as const,
  },
};

function SizeStep({ data, onChange, errors }: WizardStepProps<SizeStepData>) {
  const { getVmSizesByTier } = useCostCalculation();

  const [selectedTier, setSelectedTier] = useState<Tier>(data?.tier || 'medium');
  const [selectedSize, setSelectedSize] = useState<string>(data?.vmSize || '');
  const [tierSizes, setTierSizes] = useState<VmSizeOption[]>([]);

  // Load tier sizes when tier changes
  useEffect(() => {
    const sizes = getVmSizesByTier(selectedTier);
    setTierSizes(sizes);
    logger.debug('Loaded sizes for tier:', selectedTier, sizes.length);

    // Auto-select recommended size if none selected
    if (!selectedSize || !sizes.find(s => s.name === selectedSize)) {
      const recommended = sizes.find(s => s.recommended);
      if (recommended) {
        setSelectedSize(recommended.name);
      }
    }
  }, [selectedTier, getVmSizesByTier, selectedSize]);

  // Update parent when selection changes
  useEffect(() => {
    if (selectedSize && selectedTier) {
      onChange({
        vmSize: selectedSize,
        tier: selectedTier,
      });
    }
  }, [selectedSize, selectedTier, onChange]);

  const handleTierChange = (_event: React.MouseEvent<HTMLElement>, newTier: Tier | null) => {
    if (newTier) {
      setSelectedTier(newTier);
      setSelectedSize(''); // Clear selection when changing tier
    }
  };

  const handleSizeSelect = (size: VmSizeOption) => {
    setSelectedSize(size.name);
  };

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(price);
  };

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 1 }}>
        Choose VM Size
      </Typography>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Select the compute capacity for your virtual machine. You can resize it later if needed.
      </Typography>

      {/* Tier Selection */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
          Select Tier
        </Typography>
        <ToggleButtonGroup
          value={selectedTier}
          exclusive
          onChange={handleTierChange}
          fullWidth
          sx={{ mb: 2 }}
        >
          {Object.entries(TIER_INFO).map(([tier, info]) => (
            <ToggleButton
              key={tier}
              value={tier}
              sx={{
                '&.Mui-selected': {
                  backgroundColor: info.color,
                  color: 'white',
                  '&:hover': {
                    backgroundColor: info.color,
                    opacity: 0.9,
                  },
                },
              }}
            >
              <Box sx={{ textAlign: 'center' }}>
                <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                  {info.label}
                </Typography>
                <Typography variant="caption" sx={{ display: 'block', opacity: 0.8 }}>
                  {info.description}
                </Typography>
              </Box>
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Box>

      {/* Size Options Grid */}
      <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
        Available Sizes
      </Typography>

      <Grid container spacing={2} sx={{ mb: 2 }}>
        {tierSizes.map((size) => {
          const isSelected = selectedSize === size.name;

          return (
            <Grid item xs={12} sm={6} key={size.name}>
              <Card
                variant="outlined"
                sx={{
                  position: 'relative',
                  borderColor: isSelected ? 'primary.main' : 'divider',
                  borderWidth: isSelected ? 2 : 1,
                  backgroundColor: isSelected ? 'action.selected' : 'background.paper',
                }}
              >
                <CardActionArea onClick={() => handleSizeSelect(size)}>
                  <CardContent>
                    {/* Size Name & Recommended Badge */}
                    <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                      <Typography variant="h6" component="div">
                        {size.name}
                      </Typography>
                      {size.recommended && (
                        <Chip
                          label="Recommended"
                          size="small"
                          color="primary"
                          icon={<CheckCircleIcon />}
                        />
                      )}
                    </Stack>

                    {/* Specs */}
                    <Stack spacing={0.5} sx={{ mb: 2 }}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <SpeedIcon fontSize="small" color="action" />
                        <Typography variant="body2" color="text.secondary">
                          {size.vCPUs} vCPU{size.vCPUs > 1 ? 's' : ''}
                        </Typography>
                      </Stack>

                      <Stack direction="row" spacing={1} alignItems="center">
                        <MemoryIcon fontSize="small" color="action" />
                        <Typography variant="body2" color="text.secondary">
                          {size.memoryGiB} GiB RAM
                        </Typography>
                      </Stack>

                      <Stack direction="row" spacing={1} alignItems="center">
                        <StorageIcon fontSize="small" color="action" />
                        <Typography variant="body2" color="text.secondary">
                          {size.tempStorageGiB} GiB Temp Storage
                        </Typography>
                      </Stack>
                    </Stack>

                    {/* Pricing */}
                    <Box
                      sx={{
                        borderTop: 1,
                        borderColor: 'divider',
                        pt: 1.5,
                      }}
                    >
                      <Typography variant="body2" color="text.secondary">
                        {formatPrice(size.pricePerHour)}/hour
                      </Typography>
                      <Typography variant="body1" sx={{ fontWeight: 'bold' }}>
                        ~{formatPrice(size.pricePerMonth)}/month
                      </Typography>
                    </Box>

                    {/* Selected Indicator */}
                    {isSelected && (
                      <CheckCircleIcon
                        color="primary"
                        sx={{
                          position: 'absolute',
                          top: 8,
                          right: 8,
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

      {/* Info Alert */}
      <Alert severity="info">
        <Typography variant="body2">
          <strong>Tip:</strong> You can resize your VM later, but it will require a restart. Start with a smaller size if unsure.
        </Typography>
      </Alert>
    </Box>
  );
}

export default SizeStep;
