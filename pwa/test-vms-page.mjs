import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: false }); // Non-headless to use existing auth
  const context = await browser.newContext({
    storageState: '.auth-state.json' // Will try to load existing auth
  }).catch(() => browser.newContext()); // Fallback if no auth state

  const page = await context.newPage();

  // Capture all errors and requests
  const consoleMessages = [];
  page.on('console', msg => {
    consoleMessages.push(`[${msg.type()}] ${msg.text()}`);
  });

  const apiRequests = [];
  page.on('request', request => {
    if (request.url().includes('azure.com') || request.url().includes('microsoft')) {
      apiRequests.push({
        method: request.method(),
        url: request.url(),
      });
    }
  });

  const apiResponses = [];
  page.on('response', async response => {
    if (response.url().includes('azure.com') || response.url().includes('microsoft')) {
      const status = response.status();
      apiResponses.push({
        url: response.url(),
        status,
        statusText: response.statusText(),
      });
    }
  });

  console.log('🏴‍☠️ Navigating to http://localhost:3000...');
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });

  console.log('📸 Taking screenshot of dashboard...');
  await page.screenshot({ path: 'dashboard.png', fullPage: true });

  console.log('\n=== 📄 DASHBOARD PAGE CONTENT ===');
  const dashboardText = await page.textContent('body');
  console.log(dashboardText.substring(0, 500));

  // Look for "view vms" button
  console.log('\n🔍 Looking for "view vms" button...');
  const viewVmsButton = page.getByRole('button', { name: /view vms/i });
  const buttonCount = await viewVmsButton.count();
  console.log(`   Found ${buttonCount} matching button(s)`);

  if (buttonCount > 0) {
    console.log('🖱️  Clicking "View VMs" button...');
    await viewVmsButton.click();

    // Wait for navigation or content change
    await page.waitForTimeout(2000);

    console.log('📸 Taking screenshot of VMs page...');
    await page.screenshot({ path: 'vms-page.png', fullPage: true });

    console.log('\n=== 📄 VMS PAGE CONTENT ===');
    const vmsPageText = await page.textContent('body');
    console.log(vmsPageText);

    // Check for loading indicators
    const loadingElements = await page.locator('.loading, .spinner, [class*="progress"]').all();
    console.log(`\n⏳ Loading indicators found: ${loadingElements.length}`);

    // Check for error messages
    const errorElements = await page.locator('[class*="error"], [class*="Error"], .alert-error').all();
    console.log(`❌ Error elements found: ${errorElements.length}`);
    for (const el of errorElements) {
      const text = await el.textContent();
      console.log(`   Error: ${text}`);
    }

    // Check URL
    const currentUrl = page.url();
    console.log(`\n🌐 Current URL: ${currentUrl}`);
  }

  // Report API activity
  console.log('\n=== 🔗 API REQUESTS ===');
  if (apiRequests.length === 0) {
    console.log('No API requests to Azure/Microsoft detected!');
  } else {
    apiRequests.forEach((req, i) => {
      console.log(`${i + 1}. ${req.method} ${req.url}`);
    });
  }

  console.log('\n=== 📡 API RESPONSES ===');
  if (apiResponses.length === 0) {
    console.log('No API responses from Azure/Microsoft');
  } else {
    apiResponses.forEach((res, i) => {
      console.log(`${i + 1}. ${res.status} ${res.statusText} - ${res.url.substring(0, 80)}...`);
    });
  }

  console.log('\n=== 💬 CONSOLE MESSAGES ===');
  consoleMessages.forEach((msg, i) => {
    if (i < 20) { // First 20 messages
      console.log(msg);
    }
  });

  await browser.close();
  console.log('\n✅ Investigation complete');
})();
