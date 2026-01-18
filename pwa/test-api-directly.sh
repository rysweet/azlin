#!/bin/bash

echo "🏴‍☠️ Testing Azure API calls directly (simulating what PWA would do)"
echo ""

# Get token using az CLI (simulating MSAL)
echo "🔑 Getting Azure Management API token..."
TOKEN=$(az account get-access-token --resource https://management.azure.com --query accessToken -o tsv)
echo "✅ Token obtained (${#TOKEN} chars)"
echo ""

# Get subscription ID from env
SUBSCRIPTION_ID="9b00bc5e-9abc-45de-9958-02a9d9a277b16"
echo "📋 Using subscription: $SUBSCRIPTION_ID"
echo ""

# Test 1: List ALL VMs in subscription (what PWA does)
echo "=== TEST 1: List ALL VMs in Subscription ==="
echo "Endpoint: /subscriptions/$SUBSCRIPTION_ID/providers/Microsoft.Compute/virtualMachines"
echo ""

RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://management.azure.com/subscriptions/$SUBSCRIPTION_ID/providers/Microsoft.Compute/virtualMachines?api-version=2023-03-01")

HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '$d')

echo "HTTP Status: $HTTP_STATUS"

if echo "$BODY" | jq -e '.error' > /dev/null 2>&1; then
  echo "❌ ERROR RESPONSE:"
  echo "$BODY" | jq '.error'
else
  echo "✅ SUCCESS - VMs returned:"
  echo "$BODY" | jq '{vmCount: (.value | length), vms: [.value[] | {name, resourceGroup: (.id | split("/")[4]), location}]}'
fi

echo ""
echo "=== TEST 2: List VMs with managed-by=azlin tag filter ==="
echo "Note: REST API doesn't support tag filtering in query params"
echo "Need to: fetch all VMs, then filter client-side by tags.\"managed-by\"==\"azlin\""
echo ""

if [ "$HTTP_STATUS" = "200" ]; then
  echo "Filtering for managed-by=azlin tags..."
  echo "$BODY" | jq '.value[] | select(.tags."managed-by" == "azlin") | {name, resourceGroup: (.id | split("/")[4])}'
fi

echo ""
echo "=== TEST 3: Check what az vm list actually calls ==="
az vm list --query "[0]" -o json 2>&1 | jq '{name, id, location}' | head -10

echo ""
echo "✅ API test complete"
