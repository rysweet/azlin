/**
 * VM Create Wizard Page
 *
 * Route wrapper for the VM creation wizard.
 * Provides page-level structure and navigation.
 *
 * Philosophy:
 * - Single responsibility: Page-level routing
 * - Delegates wizard logic to VmWizardContainer
 * - Minimal wrapper, maximum delegation
 */

import { Box, AppBar, Toolbar, Typography, IconButton } from '@mui/material';
import { ArrowBack as ArrowBackIcon } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import VmWizardContainer from '../components/VmWizard/VmWizardContainer';

function VMCreateWizardPage() {
  const navigate = useNavigate();

  const handleBack = () => {
    navigate('/vms');
  };

  return (
    <Box sx={{ flexGrow: 1 }}>
      {/* Page Header */}
      <AppBar position="static" color="default" elevation={1}>
        <Toolbar>
          <IconButton
            edge="start"
            color="inherit"
            onClick={handleBack}
            sx={{ mr: 2 }}
            aria-label="back to vm list"
          >
            <ArrowBackIcon />
          </IconButton>

          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Create Virtual Machine
          </Typography>
        </Toolbar>
      </AppBar>

      {/* Wizard Container */}
      <VmWizardContainer />
    </Box>
  );
}

export default VMCreateWizardPage;
