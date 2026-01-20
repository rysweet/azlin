/**
 * VM Wizard - Authentication Step (Step 5 of 6)
 *
 * SSH authentication configuration:
 * - Username (admin account)
 * - SSH public key (paste or upload)
 * - Key validation (RSA/Ed25519 format check)
 *
 * Philosophy:
 * - Single responsibility: Authentication setup
 * - SSH key-only authentication (no password auth)
 * - Real-time validation with clear feedback
 */

import { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  TextField,
  Button,
  Alert,
  Paper,
  Stack,
  Tabs,
  Tab,
  IconButton,
  Tooltip,
} from '@mui/material';
import {
  Upload as UploadIcon,
  ContentCopy as CopyIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
} from '@mui/icons-material';
import { WizardStepProps, AuthStepData } from '../types/VmWizardTypes';
import { validateSshPublicKey } from '../../../utils/ssh-key-validator';
import { createLogger } from '../../../utils/logger';

const logger = createLogger('[AuthStep]');

const DEFAULT_USERNAME = 'azureuser';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`ssh-tabpanel-${index}`}
      aria-labelledby={`ssh-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 2 }}>{children}</Box>}
    </div>
  );
}

function AuthStep({ data, onChange, errors }: WizardStepProps<AuthStepData>) {
  const [username, setUsername] = useState(data?.username || DEFAULT_USERNAME);
  const [sshPublicKey, setSshPublicKey] = useState(data?.sshPublicKey || '');
  const [sshKeyErrors, setSshKeyErrors] = useState<string[]>([]);
  const [tabValue, setTabValue] = useState(0);
  const [uploadedFileName, setUploadedFileName] = useState<string>('');

  // Validate SSH key on change
  useEffect(() => {
    if (!sshPublicKey.trim()) {
      setSshKeyErrors([]);
      return;
    }

    const result = validateSshPublicKey(sshPublicKey);
    setSshKeyErrors(result.errors);

    if (result.valid) {
      logger.debug('SSH key validated:', result.keyType);
    }
  }, [sshPublicKey]);

  // Update parent when data changes
  useEffect(() => {
    const isValid =
      username.length >= 3 &&
      username.length <= 32 &&
      sshPublicKey.trim().length > 0 &&
      sshKeyErrors.length === 0;

    if (isValid) {
      onChange({
        username,
        sshPublicKey: sshPublicKey.trim(),
      });
    }
  }, [username, sshPublicKey, sshKeyErrors, onChange]);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setSshPublicKey(content.trim());
      setUploadedFileName(file.name);
      logger.debug('SSH key loaded from file:', file.name);
    };
    reader.onerror = () => {
      logger.error('Failed to read file:', file.name);
    };
    reader.readAsText(file);

    // Reset the input so the same file can be uploaded again
    event.target.value = '';
  };

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      setSshPublicKey(text.trim());
      logger.debug('SSH key pasted from clipboard');
    } catch (err) {
      logger.error('Failed to read clipboard:', err);
    }
  };

  const isKeyValid = sshPublicKey.trim().length > 0 && sshKeyErrors.length === 0;

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 1 }}>
        Authentication
      </Typography>

      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Configure SSH key authentication for secure access to your VM. Password authentication is disabled for security.
      </Typography>

      {/* Username */}
      <TextField
        label="Username"
        fullWidth
        required
        value={username}
        onChange={(e) => setUsername(e.target.value.toLowerCase())}
        helperText="Admin username (3-32 characters, lowercase letters and numbers)"
        placeholder={DEFAULT_USERNAME}
        sx={{ mb: 3 }}
        autoFocus
        inputProps={{
          pattern: '[a-z0-9]+',
          minLength: 3,
          maxLength: 32,
        }}
      />

      {/* SSH Key Input */}
      <Paper elevation={0} sx={{ p: 2, mb: 2, bgcolor: 'background.default' }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>
            SSH Public Key
          </Typography>

          {isKeyValid && (
            <Tooltip title="SSH key is valid">
              <CheckCircleIcon color="success" />
            </Tooltip>
          )}
        </Stack>

        {/* Tabs for Paste vs Upload */}
        <Tabs value={tabValue} onChange={handleTabChange} sx={{ mb: 2 }}>
          <Tab label="Paste Key" />
          <Tab label="Upload File" />
        </Tabs>

        {/* Paste Tab */}
        <TabPanel value={tabValue} index={0}>
          <TextField
            fullWidth
            multiline
            rows={6}
            value={sshPublicKey}
            onChange={(e) => setSshPublicKey(e.target.value)}
            placeholder="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB... or ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA..."
            error={sshKeyErrors.length > 0}
            helperText={
              sshKeyErrors.length > 0
                ? sshKeyErrors[0]
                : 'Paste your SSH public key here (id_rsa.pub or id_ed25519.pub)'
            }
            InputProps={{
              endAdornment: (
                <IconButton onClick={handlePaste} size="small">
                  <Tooltip title="Paste from clipboard">
                    <CopyIcon />
                  </Tooltip>
                </IconButton>
              ),
            }}
          />
        </TabPanel>

        {/* Upload Tab */}
        <TabPanel value={tabValue} index={1}>
          <Stack spacing={2}>
            <Button
              variant="outlined"
              component="label"
              startIcon={<UploadIcon />}
              fullWidth
            >
              Choose SSH Key File
              <input
                type="file"
                hidden
                accept=".pub"
                onChange={handleFileUpload}
              />
            </Button>

            {uploadedFileName && (
              <Alert severity="success" icon={<CheckCircleIcon />}>
                Loaded: {uploadedFileName}
              </Alert>
            )}

            {sshPublicKey && (
              <TextField
                fullWidth
                multiline
                rows={4}
                value={sshPublicKey}
                InputProps={{ readOnly: true }}
                helperText="Preview of uploaded key"
              />
            )}
          </Stack>
        </TabPanel>
      </Paper>

      {/* Validation Errors from Parent */}
      {errors && errors.length > 0 && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {errors.map((error, i) => (
            <div key={i}>{error}</div>
          ))}
        </Alert>
      )}

      {/* Info Alerts */}
      <Alert severity="info" icon={<InfoIcon />} sx={{ mb: 2 }}>
        <Typography variant="body2">
          <strong>Don't have an SSH key?</strong> Generate one on your local machine:
        </Typography>
        <Paper
          elevation={0}
          sx={{
            mt: 1,
            p: 1,
            bgcolor: 'grey.900',
            color: 'grey.100',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
          }}
        >
          ssh-keygen -t ed25519 -C "your_email@example.com"
        </Paper>
        <Typography variant="body2" sx={{ mt: 1 }}>
          Then paste the contents of <code>~/.ssh/id_ed25519.pub</code>
        </Typography>
      </Alert>

      <Alert severity="warning" icon={<ErrorIcon />}>
        <Typography variant="body2">
          <strong>Important:</strong> Save your private key securely! You'll need it to connect to your VM.
          The public key you provide here will be the only way to access your VM.
        </Typography>
      </Alert>
    </Box>
  );
}

export default AuthStep;
