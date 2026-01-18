import { http, HttpResponse } from 'msw';

const AZURE_BASE_URL = 'https://management.azure.com';
const AZURE_AD_URL = 'https://login.microsoftonline.com';

export const handlers = [
  // Azure AD Device Code Flow - Request device code
  http.post(`${AZURE_AD_URL}/common/oauth2/v2.0/devicecode`, () => {
    return HttpResponse.json({
      device_code: 'mock_device_code_12345',
      user_code: 'ABCD1234',
      verification_uri: 'https://microsoft.com/devicelogin',
      expires_in: 900,
      interval: 5,
      message: 'To sign in, use a web browser to open the page https://microsoft.com/devicelogin and enter the code ABCD1234 to authenticate.',
    });
  }),

  // Azure AD Token Polling
  http.post(`${AZURE_AD_URL}/common/oauth2/v2.0/token`, async ({ request }) => {
    const body = await request.text();
    const params = new URLSearchParams(body);

    if (params.get('grant_type') === 'refresh_token') {
      return HttpResponse.json({
        access_token: 'mock_refreshed_access_token',
        refresh_token: 'mock_refreshed_refresh_token',
        expires_in: 3600,
        token_type: 'Bearer',
      });
    }

    // Device code grant
    return HttpResponse.json({
      access_token: 'mock_access_token',
      refresh_token: 'mock_refresh_token',
      expires_in: 3600,
      token_type: 'Bearer',
    });
  }),

  // List VMs
  http.get(`${AZURE_BASE_URL}/subscriptions/:subscriptionId/providers/Microsoft.Compute/virtualMachines`, ({ params }) => {
    return HttpResponse.json({
      value: [
        {
          id: '/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.Compute/virtualMachines/vm-test-1',
          name: 'vm-test-1',
          location: 'eastus',
          properties: {
            hardwareProfile: { vmSize: 'Standard_B2s' },
            storageProfile: {
              osDisk: { osType: 'Linux' },
            },
            networkProfile: {
              networkInterfaces: [
                { properties: { privateIPAddress: '10.0.0.4' } },
              ],
            },
            instanceView: {
              statuses: [
                { code: 'PowerState/running' },
              ],
            },
          },
          tags: { 'azlin-managed': 'true' },
        },
        {
          id: '/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.Compute/virtualMachines/vm-test-2',
          name: 'vm-test-2',
          location: 'westus2',
          properties: {
            hardwareProfile: { vmSize: 'Standard_D2s_v3' },
            storageProfile: {
              osDisk: { osType: 'Linux' },
            },
            networkProfile: {
              networkInterfaces: [
                { properties: { privateIPAddress: '10.0.0.5' } },
              ],
            },
            instanceView: {
              statuses: [
                { code: 'PowerState/deallocated' },
              ],
            },
          },
          tags: { 'azlin-managed': 'true' },
        },
      ],
    });
  }),

  // Start VM
  http.post(`${AZURE_BASE_URL}/subscriptions/:subscriptionId/resourceGroups/:resourceGroup/providers/Microsoft.Compute/virtualMachines/:vmName/start`, () => {
    return HttpResponse.json({}, { status: 202 });
  }),

  // Stop/Deallocate VM
  http.post(`${AZURE_BASE_URL}/subscriptions/:subscriptionId/resourceGroups/:resourceGroup/providers/Microsoft.Compute/virtualMachines/:vmName/deallocate`, () => {
    return HttpResponse.json({}, { status: 202 });
  }),

  // Power Off VM
  http.post(`${AZURE_BASE_URL}/subscriptions/:subscriptionId/resourceGroups/:resourceGroup/providers/Microsoft.Compute/virtualMachines/:vmName/powerOff`, () => {
    return HttpResponse.json({}, { status: 202 });
  }),

  // Run Command API (for tmux)
  http.post(`${AZURE_BASE_URL}/subscriptions/:subscriptionId/resourceGroups/:resourceGroup/providers/Microsoft.Compute/virtualMachines/:vmName/runCommand`, async ({ request }) => {
    const body = await request.json() as { commandId: string; script: string[] };

    const script = body.script[0];

    // Simulate tmux list sessions
    if (script.includes('tmux list-windows')) {
      return HttpResponse.json({
        value: [
          {
            code: 'ComponentStatus/StdOut/succeeded',
            displayStatus: 'Provisioning succeeded',
            message: 'SESSION_INFO:\n0:main:1\n1:editor:0\nPANE_CONTENT:\n$ ls -la\ntotal 48\n-rw-r--r-- 1 user user 1234 Jan 15 10:00 file.txt',
          },
          {
            code: 'ComponentStatus/StdErr/succeeded',
            message: '',
          },
        ],
      });
    }

    // Simulate tmux send-keys
    if (script.includes('tmux send-keys')) {
      return HttpResponse.json({
        value: [
          {
            code: 'ComponentStatus/StdOut/succeeded',
            displayStatus: 'Provisioning succeeded',
            message: 'Command executed successfully',
          },
          {
            code: 'ComponentStatus/StdErr/succeeded',
            message: '',
          },
        ],
      });
    }

    // Default response
    return HttpResponse.json({
      value: [
        {
          code: 'ComponentStatus/StdOut/succeeded',
          displayStatus: 'Provisioning succeeded',
          message: 'Command executed',
        },
      ],
    });
  }),

  // Cost Management API
  http.post(`${AZURE_BASE_URL}/subscriptions/:subscriptionId/providers/Microsoft.CostManagement/query`, () => {
    return HttpResponse.json({
      properties: {
        rows: [
          [100.50, 20250115],
          [89.25, 20250114],
          [95.00, 20250113],
        ],
        columns: [
          { name: 'Cost', type: 'Number' },
          { name: 'Date', type: 'Number' },
        ],
      },
    });
  }),
];
