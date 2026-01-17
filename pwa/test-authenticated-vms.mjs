import { chromium } from 'playwright';

(async () => {
  console.log('🏴‍☠️ Starting authenticated VMs page test...\n');

  const browser = await chromium.launch({
    headless: false,  // Non-headless to see what's happening
    slowMo: 500       // Slow down for visibility
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 }
  });

  const page = await context.newPage();

  // Comprehensive logging
  const allLogs = [];

  page.on('console', msg => {
    const text = `[CONSOLE ${msg.type()}] ${msg.text()}`;
    allLogs.push(text);
    console.log(text);
  });

  page.on('pageerror', error => {
    const text = `[PAGE ERROR] ${error.message}`;
    allLogs.push(text);
    console.log(text);
  });

  page.on('requestfailed', request => {
    const text = `[REQUEST FAILED] ${request.method()} ${request.url()} - ${request.failure().errorText}`;
    allLogs.push(text);
    console.log(text);
  });

  page.on('response', async response => {
    const url = response.url();
    if (url.includes('management.azure.com') || url.includes('virtualMachines')) {
      const text = `[API RESPONSE] ${response.status()} ${response.request().method()} ${url}`;
      allLogs.push(text);
      console.log(text);

      // Log response body for Azure API calls
      if (response.status() !== 200) {
        try {
          const body = await response.text();
          console.log(`   Response body: ${body.substring(0, 200)}`);
        } catch (e) {
          // Ignore if can't read body
        }
      }
    }
  });

  try {
    console.log('📱 Navigating to PWA...');
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });

    await page.waitForTimeout(2000);
    await page.screenshot({ path: 'test-1-loaded.png' });
    console.log('📸 Screenshot 1: Page loaded\n');

    // Check if authenticated or need to login
    const currentUrl = page.url();
    console.log(`Current URL: ${currentUrl}`);

    const pageText = await page.textContent('body');
    console.log(`Page content preview: ${pageText.substring(0, 200)}...\n`);

    // If we see dashboard, click View VMs
    const viewVmsButton = page.getByRole('button', { name: /view vms/i });
    const hasButton = await viewVmsButton.count() > 0;

    if (hasButton) {
      console.log('✅ Found "View VMs" button on dashboard');
      console.log('🖱️  Clicking "View VMs"...\n');
      await viewVmsButton.click();
      await page.waitForTimeout(3000);

      await page.screenshot({ path: 'test-2-vms-page.png' });
      console.log('📸 Screenshot 2: VMs page\n');

      // Check what's on the VMs page
      const vmsPageText = await page.textContent('body');
      console.log('=== VMS PAGE CONTENT ===');
      console.log(vmsPageText);
      console.log();

      // Check for loading, error, or empty state
      const hasLoading = await page.locator('text=/loading/i').count() > 0;
      const hasError = await page.locator('[class*="error"]').count() > 0;
      const hasVMs = await page.locator('.MuiListItem-root').count();

      console.log('📊 VMs Page Status:');
      console.log(`   Loading indicator: ${hasLoading}`);
      console.log(`   Error messages: ${hasError}`);
      console.log(`   VM list items: ${hasVMs}`);
    } else {
      console.log('❌ No "View VMs" button found - might be on login page');
      const hasSignIn = await page.getByRole('button', { name: /sign in/i }).count() > 0;
      console.log(`   Has "Sign In" button: ${hasSignIn}`);
    }

    console.log('\n=== ALL LOGS SUMMARY ===');
    allLogs.forEach((log, i) => {
      if (i < 50) { // First 50 logs
        console.log(log);
      }
    });

    // Keep browser open for manual inspection
    console.log('\n⏸️  Browser will stay open for 30 seconds for inspection...');
    await page.waitForTimeout(30000);

  } catch (error) {
    console.error('❌ Test failed:', error.message);
  } finally {
    await browser.close();
    console.log('\n✅ Test complete');
  }
})();
