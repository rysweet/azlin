// import React from 'react';
import { useParams } from 'react-router-dom';
import { Box, Typography, Button } from '@mui/material';
import { useSelector, useDispatch } from 'react-redux';
import { AppDispatch } from '../store/store';
import { selectVMById, startVM, stopVM } from '../store/vm-store';

function VMDetailPage() {
  const { vmId } = useParams<{ vmId: string }>();
  const dispatch = useDispatch<AppDispatch>();
  const vm = useSelector((state: any) => selectVMById(state, decodeURIComponent(vmId || '')));

  if (!vm) {
    return <Typography>VM not found</Typography>;
  }

  const handleStart = () => {
    dispatch(startVM({ resourceGroup: vm.resourceGroup, vmName: vm.name }));
  };

  const handleStop = () => {
    dispatch(stopVM({ resourceGroup: vm.resourceGroup, vmName: vm.name, deallocate: true }));
  };

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="h4" gutterBottom>
        {vm.name}
      </Typography>
      <Typography>Power State: {vm.powerState}</Typography>
      <Typography>Size: {vm.size}</Typography>
      <Typography>Location: {vm.location}</Typography>
      {vm.privateIP && <Typography>Private IP: {vm.privateIP}</Typography>}
      <Box sx={{ mt: 2 }}>
        <Button variant="contained" onClick={handleStart} sx={{ mr: 1 }}>
          Start
        </Button>
        <Button variant="outlined" onClick={handleStop}>
          Stop
        </Button>
      </Box>
    </Box>
  );
}

export default VMDetailPage;
