# Azlin Mobile PWA Architecture

**Technical architecture and design decisions for the Azlin Mobile PWA.**

This document explains how the Azlin Mobile PWA works under the hood, including authentication flows, API integration, and architectural patterns.

## Contents

- [System Overview](#system-overview)
- [Authentication Architecture](#authentication-architecture)
- [API Integration](#api-integration)
- [Tmux Integration](#tmux-integration)
- [State Management](#state-management)
- [Offline Architecture](#offline-architecture)
- [Security Model](#security-model)

## System Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     iPhone / iPad Browser                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │           Azlin Mobile PWA (React)                    │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │  UI Layer        │  State Management │  Service Worker│  │
│  │  - React Router  │  - Redux          │  - Caching     │  │
│  │  - Components    │  - IndexedDB      │  - Sync        │  │
│  │  - Hooks         │  - Local Storage  │  - Offline     │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │  API Layer       │  Auth Layer       │  Sync Layer    │  │
│  │  - Azure SDK     │  - OAuth2 Device  │  - Queue       │  │
│  │  - REST Client   │  - Token Refresh  │  - Retry       │  │
│  └──────────────────────────────────────────────────────┘  │
│                          ↕ HTTPS                            │
└─────────────────────────────────────────────────────────────┘
                           ↕
┌─────────────────────────────────────────────────────────────┐
│                   Azure Cloud Services                       │
├─────────────────────────────────────────────────────────────┤
│  Azure AD        │  Compute API    │  Cost Management API   │
│  - Device Auth   │  - VM Ops       │  - Cost Queries        │
│  - Token Service │  - Run Command  │  - Budget Alerts       │
│                  │                 │                        │
│  Azure Bastion   │  Azure Monitor  │  Storage Account       │
│  - Private IP    │  - Metrics      │  - PWA Assets          │
│  - SSH Tunnel    │  - Logs         │  - Static Hosting      │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

**Frontend**:
- React 18 (UI framework)
- Redux Toolkit (state management)
- React Router 6 (routing)
- Material-UI (component library)
- Axios (HTTP client)

**Authentication**:
- @azure/identity (Azure AD OAuth2)
- @azure/msal-browser (device code flow)

**Azure APIs**:
- @azure/arm-compute (VM management)
- @azure/arm-monitor (metrics)
- @azure/arm-costmanagement (cost tracking)
- Azure REST API (Run Command)

**PWA Features**:
- Workbox (service worker)
- IndexedDB (local storage)
- Web Push API (notifications)

## Authentication Architecture

### Device Code Flow

Azure AD device code flow is optimized for devices without keyboards or reliable input methods (like phones):

```
┌─────────┐                                    ┌──────────┐
│  PWA    │                                    │ Azure AD │
└────┬────┘                                    └─────┬────┘
     │                                               │
     │ 1. Request device code                       │
     ├──────────────────────────────────────────────>│
     │                                               │
     │ 2. Device code + user code                   │
     │<──────────────────────────────────────────────┤
     │    { device_code, user_code, verification_uri }
     │                                               │
     │ 3. Display user code to user                 │
     │    (e.g., "A1B2C3D4")                        │
     │                                               │
     │ 4. Open browser to verification_uri          │
     │    (microsoft.com/devicelogin)               │
     │                                               │
     │                              ┌──────────┐    │
     │                              │ Browser  │    │
     │                              └────┬─────┘    │
     │                                   │          │
     │              5. User enters code  │          │
     │              and authenticates    ├──────────>│
     │                                   │          │
     │              6. Success page      │<──────────┤
     │                                   │          │
     │ 7. Poll for token (every 5-15s with backoff) │
     ├──────────────────────────────────────────────>│
     │                                               │
     │ 8. Access token + refresh token              │
     │<──────────────────────────────────────────────┤
     │                                               │
     │ 9. Store tokens securely                     │
     │    (IndexedDB with iOS encryption)           │
     │                                               │
```

**Device Code Polling Strategy**:
- Initial interval: 5 seconds
- Max interval: 15 seconds
- Uses exponential backoff to avoid rate limiting
- Device code expires after 15 minutes

### Implementation

**Device Code Request**:
```javascript
// src/auth/deviceCodeFlow.js
import { DeviceCodeCredential } from '@azure/identity';

export async function initiateDeviceCodeAuth() {
  const credential = new DeviceCodeCredential({
    tenantId: process.env.REACT_APP_AZURE_TENANT_ID,
    clientId: process.env.REACT_APP_AZURE_CLIENT_ID,
    userPromptCallback: (info) => {
      // Display code to user
      return displayDeviceCode(info.userCode, info.verificationUri);
    }
  });

  // Get token (triggers callback above)
  const token = await credential.getToken(
    'https://management.azure.com/.default'
  );

  return {
    accessToken: token.token,
    expiresOn: token.expiresOnTimestamp
  };
}
```

**Token Storage**:
```javascript
// src/auth/tokenStorage.js
import { SecureStorage } from './secureStorage';

export class TokenStorage {
  async saveTokens(accessToken, refreshToken, expiresOn) {
    // IndexedDB with automatic iOS encryption
    await SecureStorage.set('azure_access_token', accessToken);
    await SecureStorage.set('azure_refresh_token', refreshToken);
    await SecureStorage.set('azure_token_expiry', expiresOn.toString());
  }

  async getAccessToken() {
    const token = await SecureStorage.get('azure_access_token');
    const expiry = await SecureStorage.get('azure_token_expiry');

    // Check if expired
    if (Date.now() >= parseInt(expiry)) {
      return await this.refreshToken();
    }

    return token;
  }

  async refreshToken() {
    const refreshToken = await SecureStorage.get('azure_refresh_token');

    const response = await fetch('https://login.microsoftonline.com/common/oauth2/v2.0/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        client_id: process.env.REACT_APP_AZURE_CLIENT_ID,
        grant_type: 'refresh_token',
        refresh_token: refreshToken,
        scope: 'https://management.azure.com/.default'
      })
    });

    const data = await response.json();
    await this.saveTokens(data.access_token, data.refresh_token,
                          Date.now() + (data.expires_in * 1000));

    return data.access_token;
  }
}
```

**Token Storage Security**:
- Access tokens: Stored in memory only (cleared on page unload)
- Refresh tokens: Stored in IndexedDB (encrypted by iOS automatically)
- **Note**: PWAs on iOS don't have direct Keychain access. IndexedDB provides automatic encryption through the iOS secure storage layer.

```javascript
```

## API Integration

### Azure REST API Client

**Base Client**:
```javascript
// src/api/azureClient.js
import axios from 'axios';
import { TokenStorage } from '../auth/tokenStorage';

export class AzureClient {
  constructor() {
    this.baseURL = 'https://management.azure.com';
    this.tokenStorage = new TokenStorage();
    this.subscriptionId = process.env.REACT_APP_AZURE_SUBSCRIPTION_ID;
  }

  async request(method, path, data = null) {
    const token = await this.tokenStorage.getAccessToken();

    const response = await axios({
      method,
      url: `${this.baseURL}${path}`,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      },
      params: { 'api-version': '2023-03-01' },
      data
    });

    return response.data;
  }

  // Convenience methods
  async get(path) { return this.request('GET', path); }
  async post(path, data) { return this.request('POST', path, data); }
  async put(path, data) { return this.request('PUT', path, data); }
  async delete(path) { return this.request('DELETE', path); }
}
```

### VM Management API

**List VMs**:
```javascript
// src/api/vmApi.js
export class VMApi extends AzureClient {
  async listVMs(resourceGroup = null) {
    const path = resourceGroup
      ? `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Compute/virtualMachines`
      : `/subscriptions/${this.subscriptionId}/providers/Microsoft.Compute/virtualMachines`;

    const result = await this.get(path);
    return result.value.map(vm => this.parseVM(vm));
  }

  parseVM(raw) {
    return {
      id: raw.id,
      name: raw.name,
      resourceGroup: raw.id.split('/')[4],
      location: raw.location,
      size: raw.properties.hardwareProfile.vmSize,
      powerState: this.extractPowerState(raw),
      privateIP: raw.properties.networkProfile.networkInterfaces[0]?.privateIPAddress,
      osType: raw.properties.storageProfile.osDisk.osType
    };
  }
}
```

**Create VM**:
```javascript
async createVM(resourceGroup, vmName, config) {
  const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Compute/virtualMachines/${vmName}`;

  const body = {
    location: config.location,
    properties: {
      hardwareProfile: { vmSize: config.size },
      storageProfile: {
        imageReference: this.getImageReference(config.image),
        osDisk: {
          createOption: 'FromImage',
          managedDisk: { storageAccountType: 'Premium_LRS' },
          diskSizeGB: config.diskSize
        }
      },
      osProfile: {
        computerName: vmName,
        adminUsername: config.adminUsername,
        linuxConfiguration: {
          disablePasswordAuthentication: true,
          ssh: {
            publicKeys: [{
              path: `/home/${config.adminUsername}/.ssh/authorized_keys`,
              keyData: config.sshPublicKey
            }]
          }
        }
      },
      networkProfile: {
        networkInterfaces: [{
          id: config.networkInterfaceId,
          properties: { primary: true }
        }]
      }
    }
  };

  // Start async operation
  const result = await this.put(path, body);

  // Poll for completion
  return this.pollOperation(result.properties.provisioningState);
}
```

**Start/Stop VM**:
```javascript
async startVM(resourceGroup, vmName) {
  const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Compute/virtualMachines/${vmName}/start`;
  return this.post(path);
}

async stopVM(resourceGroup, vmName, deallocate = true) {
  const action = deallocate ? 'deallocate' : 'powerOff';
  const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Compute/virtualMachines/${vmName}/${action}`;
  return this.post(path);
}
```

## Tmux Integration

### Azure Run Command API

Azure Run Command API executes scripts on VMs without SSH:

```javascript
// src/api/runCommandApi.js
export class RunCommandApi extends AzureClient {
  async executeCommand(resourceGroup, vmName, script) {
    const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Compute/virtualMachines/${vmName}/runCommand`;

    const body = {
      commandId: 'RunShellScript',
      script: [script],
      parameters: []
    };

    const result = await this.post(path, body);
    return this.parseCommandResult(result);
  }

  parseCommandResult(result) {
    return {
      exitCode: result.value[0].code,
      stdout: result.value[0].message,
      stderr: result.value[1]?.message || '',
      executionTime: result.value[0].displayStatus
    };
  }
}
```

### Tmux Snapshot Implementation

**Capture Snapshot**:
```javascript
// src/tmux/snapshot.js
export class TmuxSnapshot {
  async captureSession(resourceGroup, vmName, sessionName) {
    const script = `
      # Check if session exists
      tmux has-session -t ${sessionName} 2>/dev/null || exit 1

      # Get session info
      echo "SESSION_INFO:"
      tmux list-windows -t ${sessionName} -F "#{window_index}:#{window_name}:#{window_active}"

      echo "PANE_CONTENT:"
      # Capture active pane (2000 lines of scrollback)
      tmux capture-pane -t ${sessionName} -p -S -2000
    `;

    const result = await this.runCommand.executeCommand(
      resourceGroup, vmName, script
    );

    return this.parseSnapshot(result.stdout);
  }

  parseSnapshot(output) {
    const lines = output.split('\n');
    const sessionInfoIndex = lines.indexOf('SESSION_INFO:');
    const paneContentIndex = lines.indexOf('PANE_CONTENT:');

    // Parse windows
    const windows = lines
      .slice(sessionInfoIndex + 1, paneContentIndex)
      .map(line => {
        const [index, name, active] = line.split(':');
        return {
          index: parseInt(index),
          name,
          active: active === '1'
        };
      });

    // Parse pane content
    const content = lines.slice(paneContentIndex + 1);

    return {
      windows,
      activeWindow: windows.find(w => w.active),
      paneContent: content,
      timestamp: Date.now()
    };
  }
}
```

**Send Keys**:
```javascript
async sendKeys(resourceGroup, vmName, sessionName, keys) {
  const script = `
    # Send keys to active pane
    tmux send-keys -t ${sessionName} "${keys}"
  `;

  const result = await this.runCommand.executeCommand(
    resourceGroup, vmName, script
  );

  if (result.exitCode !== 0) {
    throw new Error(`Failed to send keys: ${result.stderr}`);
  }

  return { success: true };
}
```

**Watch Mode**:
```javascript
// src/tmux/watcher.js
export class TmuxWatcher {
  constructor(resourceGroup, vmName, sessionName) {
    this.resourceGroup = resourceGroup;
    this.vmName = vmName;
    this.sessionName = sessionName;
    this.interval = 10000; // 10 seconds
    this.lastSnapshot = null;
    this.intervalId = null;
  }

  start(onChangeCallback) {
    this.intervalId = setInterval(async () => {
      const snapshot = await tmuxSnapshot.captureSession(
        this.resourceGroup, this.vmName, this.sessionName
      );

      if (this.lastSnapshot) {
        const diff = this.computeDiff(this.lastSnapshot, snapshot);
        if (diff.hasChanges) {
          onChangeCallback(diff);
        }
      }

      this.lastSnapshot = snapshot;
    }, this.interval);
  }

  stop() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  computeDiff(oldSnapshot, newSnapshot) {
    const changedLines = [];

    for (let i = 0; i < newSnapshot.paneContent.length; i++) {
      if (oldSnapshot.paneContent[i] !== newSnapshot.paneContent[i]) {
        changedLines.push({
          lineNumber: i,
          oldContent: oldSnapshot.paneContent[i],
          newContent: newSnapshot.paneContent[i]
        });
      }
    }

    return {
      hasChanges: changedLines.length > 0,
      linesChanged: changedLines.length,
      changedLines
    };
  }
}
```

## State Management

### Redux Store Structure

```javascript
// src/store/store.js
import { configureStore } from '@reduxjs/toolkit';
import vmReducer from './slices/vmSlice';
import tmuxReducer from './slices/tmuxSlice';
import costReducer from './slices/costSlice';
import authReducer from './slices/authSlice';
import syncReducer from './slices/syncSlice';

export const store = configureStore({
  reducer: {
    vms: vmReducer,
    tmux: tmuxReducer,
    costs: costReducer,
    auth: authReducer,
    sync: syncReducer
  }
});
```

**VM Slice**:
```javascript
// src/store/slices/vmSlice.js
import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { vmApi } from '../../api/vmApi';

export const fetchVMs = createAsyncThunk(
  'vms/fetchAll',
  async (resourceGroup) => {
    return await vmApi.listVMs(resourceGroup);
  }
);

export const startVM = createAsyncThunk(
  'vms/start',
  async ({ resourceGroup, vmName }) => {
    await vmApi.startVM(resourceGroup, vmName);
    return { resourceGroup, vmName, powerState: 'running' };
  }
);

const vmSlice = createSlice({
  name: 'vms',
  initialState: {
    items: [],
    loading: false,
    error: null,
    lastSync: null
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchVMs.pending, (state) => {
        state.loading = true;
      })
      .addCase(fetchVMs.fulfilled, (state, action) => {
        state.items = action.payload;
        state.loading = false;
        state.lastSync = Date.now();
      })
      .addCase(startVM.fulfilled, (state, action) => {
        const vm = state.items.find(
          v => v.name === action.payload.vmName
        );
        if (vm) {
          vm.powerState = action.payload.powerState;
        }
      });
  }
});

export default vmSlice.reducer;
```

### IndexedDB Persistence

```javascript
// src/db/indexedDB.js
import { openDB } from 'idb';

export class LocalDatabase {
  async init() {
    this.db = await openDB('azlin-pwa', 1, {
      upgrade(db) {
        // VMs store
        db.createObjectStore('vms', { keyPath: 'id' });

        // Tmux snapshots store
        const tmuxStore = db.createObjectStore('tmux', { keyPath: 'id' });
        tmuxStore.createIndex('vmId', 'vmId');

        // Cost data store
        db.createObjectStore('costs', { keyPath: 'date' });

        // Action queue store
        db.createObjectStore('queue', { keyPath: 'id', autoIncrement: true });
      }
    });
  }

  async saveVMs(vms) {
    const tx = this.db.transaction('vms', 'readwrite');
    await Promise.all(vms.map(vm => tx.store.put(vm)));
  }

  async getVMs() {
    return await this.db.getAll('vms');
  }

  async saveSnapshot(vmId, sessionName, snapshot) {
    await this.db.put('tmux', {
      id: `${vmId}:${sessionName}`,
      vmId,
      sessionName,
      snapshot,
      timestamp: Date.now()
    });
  }

  async getSnapshots(vmId) {
    return await this.db.getAllFromIndex('tmux', 'vmId', vmId);
  }
}
```

## Offline Architecture

### Service Worker

**Cache Strategy**:
```javascript
// src/serviceWorker.js
import { registerRoute } from 'workbox-routing';
import { CacheFirst, NetworkFirst, StaleWhileRevalidate } from 'workbox-strategies';
import { ExpirationPlugin } from 'workbox-expiration';

// App shell - cache first
registerRoute(
  ({ request }) => request.destination === 'document',
  new CacheFirst({
    cacheName: 'app-shell',
    plugins: [
      new ExpirationPlugin({ maxAgeSeconds: 7 * 24 * 60 * 60 }) // 7 days
    ]
  })
);

// API calls - network first with cache fallback
registerRoute(
  ({ url }) => url.pathname.includes('/api/'),
  new NetworkFirst({
    cacheName: 'api-cache',
    plugins: [
      new ExpirationPlugin({
        maxEntries: 50,
        maxAgeSeconds: 5 * 60 // 5 minutes
      })
    ]
  })
);

// Images - stale while revalidate
registerRoute(
  ({ request }) => request.destination === 'image',
  new StaleWhileRevalidate({
    cacheName: 'images',
    plugins: [
      new ExpirationPlugin({ maxEntries: 100 })
    ]
  })
);
```

### Action Queue

**Queue Management**:
```javascript
// src/sync/actionQueue.js
export class ActionQueue {
  async enqueue(action) {
    await db.add('queue', {
      type: action.type,
      payload: action.payload,
      timestamp: Date.now(),
      retries: 0
    });
  }

  async processQueue() {
    const actions = await db.getAll('queue');

    for (const action of actions) {
      try {
        await this.executeAction(action);
        await db.delete('queue', action.id);
      } catch (error) {
        action.retries++;
        if (action.retries >= 3) {
          // Move to failed queue
          await db.delete('queue', action.id);
          await this.logFailedAction(action, error);
        } else {
          await db.put('queue', action);
        }
      }
    }
  }

  async executeAction(action) {
    switch (action.type) {
      case 'VM_START':
        return await vmApi.startVM(action.payload.resourceGroup, action.payload.vmName);
      case 'VM_STOP':
        return await vmApi.stopVM(action.payload.resourceGroup, action.payload.vmName);
      case 'TMUX_SEND_KEYS':
        return await tmuxSnapshot.sendKeys(
          action.payload.resourceGroup,
          action.payload.vmName,
          action.payload.sessionName,
          action.payload.keys
        );
      default:
        throw new Error(`Unknown action type: ${action.type}`);
    }
  }
}
```

## Security Model

### Token Security

**Secure Storage**:
- Access tokens in memory only (cleared on page unload)
- Refresh tokens in IndexedDB (encrypted by iOS automatically)
- Never logged or sent to analytics
- **Important**: PWAs cannot directly access iOS Keychain. iOS provides automatic encryption for IndexedDB storage.

**Token Rotation**:
- Access tokens expire after 1 hour
- Refresh tokens valid for 90 days
- Automatic rotation 5 minutes before expiry

### API Security

**Request Signing**:
```javascript
// All API requests include bearer token
headers: {
  'Authorization': `Bearer ${accessToken}`,
  'Content-Type': 'application/json'
}
```

**CORS Configuration**:
```javascript
// Azure Static Web Apps staticwebapp.config.json
{
  "responseOverrides": {
    "401": {
      "redirect": "/auth/login",
      "statusCode": 302
    }
  },
  "networking": {
    "allowedIpRanges": []  // No IP restrictions (uses Azure AD)
  }
}
```

### Data Security

**Sensitive Data Handling**:
- Passwords never stored (SSH keys only)
- VM credentials never cached
- Tmux snapshots purged after 24 hours
- Cost data aggregated (no billing details)

**Encryption**:
- All API calls over HTTPS
- IndexedDB encrypted by iOS automatically
- Service worker cache encrypted

## Performance Considerations

### API Call Optimization

**Batching**:
```javascript
// Batch multiple VM operations
async batchVMOperations(operations) {
  const promises = operations.map(op =>
    this.executeOperation(op)
  );

  return await Promise.allSettled(promises);
}
```

**Caching Strategy**:
- VM list: 5-minute cache
- Tmux snapshots: 10-second cache
- Cost data: 1-hour cache
- Metrics: 1-minute cache

**Lazy Loading**:
- VM details loaded on demand
- Snapshots loaded when tab opened
- Metrics loaded when stats tab opened

### Bundle Size

**Code Splitting**:
```javascript
// Lazy load routes
const VMDetail = lazy(() => import('./pages/VMDetail'));
const CostsDashboard = lazy(() => import('./pages/CostsDashboard'));

// Route configuration
<Route path="/vms/:id" element={
  <Suspense fallback={<Loading />}>
    <VMDetail />
  </Suspense>
} />
```

**Current Bundles**:
- Main bundle: 245 KB (gzipped)
- Vendor bundle: 189 KB (gzipped)
- Route bundles: 15-30 KB each (gzipped)

## Platform Limitations

### Azure Run Command Constraints

**Timeout Limit**:
- Maximum execution time: 90 seconds
- Applies to all Run Command operations (tmux snapshots, command execution)
- Commands exceeding timeout will fail
- **Workaround**: Break long operations into smaller commands

**Best Practices**:
- Keep tmux snapshots under 2000 lines
- Avoid long-running commands
- Use tmux for persistent operations

### Cost Data Freshness

**Azure Cost Management API Lag**:
- Cost data has 24-hour freshness lag
- Today's costs may be incomplete until tomorrow
- Budget alerts trigger after delay
- Historical data is accurate

**Display Strategy**:
- Show "Estimated" label for today's costs
- Mark data with last update timestamp
- Provide "Data as of [date]" disclaimer

### Tmux Snapshot Size

**Maximum Scrollback**:
- 2000 lines per snapshot
- Larger captures risk timeout
- Older content truncated

**Configuration**:
```bash
# In VM's ~/.tmux.conf
set-option -g history-limit 2000
```

### Device Code Expiration

**Authentication Window**:
- Device code expires after 15 minutes
- User must enter code within window
- New code required after expiration

**User Experience**:
- Show countdown timer
- Clear expiration warning
- Easy retry mechanism

## Next Steps

- **[Deployment](./deployment.md)**: Deploy to Azure Static Web Apps
- **[Features](./features.md)**: Learn about all features
- **[Getting Started](./getting-started.md)**: Return to setup guide
