import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { Box, Typography, Paper, TextField, Button } from '@mui/material';
import { useDispatch, useSelector } from 'react-redux';
import { AppDispatch } from '../store/store';
import { captureSnapshot, sendKeys, selectSnapshotById } from '../store/tmux-store';

function TmuxPage() {
  const { vmId, sessionName } = useParams<{ vmId: string; sessionName: string }>();
  const dispatch = useDispatch<AppDispatch>();
  const [command, setCommand] = useState('');

  const [resourceGroup, vmName] = (vmId || '').split('/');
  const snapshotId = `${vmId}:${sessionName}`;
  const snapshot = useSelector((state: any) => selectSnapshotById(state, snapshotId));

  useEffect(() => {
    if (resourceGroup && vmName && sessionName) {
      dispatch(captureSnapshot({ resourceGroup, vmName, sessionName }));
    }
  }, [dispatch, resourceGroup, vmName, sessionName]);

  const handleSendKeys = () => {
    if (command && resourceGroup && vmName && sessionName) {
      dispatch(sendKeys({ resourceGroup, vmName, sessionName, keys: command }));
      setCommand('');
    }
  };

  return (
    <Box sx={{ p: 2 }}>
      <Typography variant="h4" gutterBottom>
        Tmux: {sessionName}
      </Typography>
      <Paper sx={{ p: 2, bgcolor: 'black', color: 'white', fontFamily: 'monospace', minHeight: 400 }}>
        {snapshot?.paneContent.map((line, idx) => (
          <div key={idx}>{line}</div>
        ))}
      </Paper>
      <Box sx={{ mt: 2, display: 'flex' }}>
        <TextField
          fullWidth
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder="Enter command..."
          onKeyPress={(e) => e.key === 'Enter' && handleSendKeys()}
        />
        <Button variant="contained" onClick={handleSendKeys} sx={{ ml: 1 }}>
          Send
        </Button>
      </Box>
    </Box>
  );
}

export default TmuxPage;
