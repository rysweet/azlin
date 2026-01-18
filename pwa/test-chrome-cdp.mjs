import { chromium } from 'playwright';

(async () => {
  console.log('🏴‍☠️ Connecting to Chrome via CDP to check subscription ID issue...\n');

  // Connect to the already-running Chrome instance
  const browser = await chromium.connectOverCDP('http://localhost:9222');
  const contexts = browser.contexts();
  const page = contexts[0].pages()[0];

  console.log('✅ Connected to Chrome page:', await page.title());
  console.log('   URL:', page.url());
  console.log('');

  // Execute JavaScript to check the subscription ID comparison issue
  const result = await page.evaluate(() => {
    // Get the env subscription ID from the actual window object
    const envSubId = window.__VITE_ENV__?.VITE_AZURE_SUBSCRIPTION_ID ||
                      import.meta?.env?.VITE_AZURE_SUBSCRIPTION_ID ||
                      '9b00bc5e-9abc-45de-9958-02a9d9a277b16'; // Fallback to known value

    // Make API call to get token's subscription
    return fetch('https://management.azure.com/subscriptions?api-version=2022-12-01', {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('msal.access_token') || 'NO_TOKEN'}`
      }
    })
    .then(r => r.json())
    .then(data => {
      if (data.value && data.value.length > 0) {
        const tokenSubId = data.value[0].subscriptionId;

        return {
          envSubId,
          tokenSubId,
          envLength: envSubId.length,
          tokenLength: tokenSubId.length,
          match: tokenSubId === envSubId,
          trimMatch: tokenSubId.trim() === envSubId.trim(),
          envBytes: Array.from(envSubId).map(c => c.charCodeAt(0)),
          tokenBytes: Array.from(tokenSubId).map(c => c.charCodeAt(0)),
        };
      }
      return { error: 'No subscriptions found', data };
    })
    .catch(err => ({ error: err.message }));
  });

  console.log('=== SUBSCRIPTION ID COMPARISON ===');
  console.log('Token subscription:', result.tokenSubId);
  console.log('Env subscription:  ', result.envSubId);
  console.log('');
  console.log('Token length:', result.tokenLength);
  console.log('Env length:  ', result.envLength);
  console.log('');
  console.log('Exact match:', result.match);
  console.log('Trim match: ', result.trimMatch);
  console.log('');

  if (result.envBytes && result.tokenBytes) {
    console.log('=== BYTE-BY-BYTE COMPARISON ===');
    const maxLen = Math.max(result.envBytes.length, result.tokenBytes.length);

    for (let i = 0; i < maxLen; i++) {
      const envByte = result.envBytes[i];
      const tokenByte = result.tokenBytes[i];

      if (envByte !== tokenByte) {
        const envChar = String.fromCharCode(envByte);
        const tokenChar = String.fromCharCode(tokenByte);
        console.log(`❌ Position ${i}: Env='${envChar}' (${envByte}) vs Token='${tokenChar}' (${tokenByte})`);
      }
    }
  }

  if (result.error) {
    console.error('\n❌ Error:', result.error);
  }

  console.log('\n✅ Investigation complete');

  // Don't close browser, just disconnect
  await browser.close();
})();
