import { chromium } from 'playwright';

(async () => {
  console.log('🏴‍☠️ Starting full authenticated flow test...\n');

  // Launch browser with persistent context to keep MSAL auth
  const userDataDir = '/tmp/playwright-azlin-test';
  const browser = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1280, height: 720 },
    args: ['--disable-blink-features=AutomationControlled']
  });

  const page = browser.pages()[0] || await browser.newPage();

  // Capture ALL console output with pirate flags
  const consoleLogs = [];
  page.on('console', msg => {
    const text = `[${msg.type().toUpperCase()}] ${msg.text()}`;
    consoleLogs.push(text);

    // Print pirate-flagged logs immediately
    if (msg.text().includes('🏴‍☠️')) {
      console.log('>>> ' + text);
    }
  });

  // Capture page errors
  page.on('pageerror', error => {
    const text = `[PAGE ERROR] ${error.message}\n${error.stack}`;
    consoleLogs.push(text);
    console.error('>>> ' + text);
  });

  // Capture network failures
  page.on('requestfailed', request => {
    const text = `[NETWORK FAIL] ${request.method()} ${request.url()} - ${request.failure().errorText}`;
    consoleLogs.push(text);
    console.error('>>> ' + text);
  });

  // Capture Azure API responses
  page.on('response', async response => {
    const url = response.url();
    if (url.includes('management.azure.com') || url.includes('login.microsoftonline.com')) {
      const status = response.status();
      const statusText = response.statusText();

      console.log(`>>> [API] ${status} ${response.request().method()} ${url.substring(0, 100)}...`);

      if (status >= 400) {
        try {
          const body = await response.text();
          console.error(`>>> [API ERROR BODY] ${body.substring(0, 500)}`);
          consoleLogs.push(`[API ERROR ${status}] ${url}\n${body}`);
        } catch (e) {
          // Can't read body
        }
      }
    }
  });

  try {
    console.log('📱 Step 1: Navigate to PWA');
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 10000 });
    await page.screenshot({ path: 'test-step-1-loaded.png' });

    const currentUrl = page.url();
    console.log(`   Current URL: ${currentUrl}\n`);

    // Check if we're on login page or dashboard
    const hasSignIn = await page.getByRole('button', { name: /sign in/i }).count() > 0;
    const hasViewVMs = await page.getByRole('button', { name: /view vms/i }).count() > 0;

    console.log(`   Has "Sign In" button: ${hasSignIn}`);
    console.log(`   Has "View VMs" button: ${hasViewVMs}\n`);

    if (hasSignIn) {
      console.log('🔐 Step 2: Need to authenticate');
      console.log('   Clicking "Sign In with Azure"...');

      const signInButton = page.getByRole('button', { name: /sign in/i });
      await signInButton.click();

      console.log('   Waiting for popup or redirect...');
      console.log('   ⏰ WAITING 60 SECONDS FOR YOU TO COMPLETE AUTH IN POPUP...\n');
      console.log('   👉 Please sign in manually in the popup window that opened!\n');

      // Wait for auth to complete (user signs in manually)
      await page.waitForTimeout(60000);

      await page.screenshot({ path: 'test-step-2-after-auth.png' });
      console.log('📸 Screenshot after auth wait\n');
    }

    // Navigate to VMs page
    const viewVmsButtonNow = page.getByRole('button', { name: /view vms/i });
    const hasViewVMsNow = await viewVmsButtonNow.count() > 0;

    if (hasViewVMsNow) {
      console.log('📋 Step 3: Navigate to VMs page');
      console.log('   Clicking "View VMs"...');
      await viewVmsButtonNow.click();

      // Wait for VMs page to load
      await page.waitForTimeout(5000);

      await page.screenshot({ path: 'test-step-3-vms-page.png', fullPage: true });
      console.log('📸 Screenshot of VMs page\n');

      // Check page state
      const url = page.url();
      const pageContent = await page.textContent('body');

      console.log(`   Current URL: ${url}`);
      console.log(`   Page content:\n${pageContent}\n`);

      // Check for specific elements
      const hasLoadingSpinner = await page.locator('text=/loading/i').count() > 0;
      const hasErrorAlert = await page.locator('[class*="MuiAlert"][class*="error"]').count() > 0;
      const hasVMListItems = await page.locator('.MuiListItem-root').count();
      const hasEmptyState = await page.locator('text=/no vms found/i').count() > 0;

      console.log('📊 VMs Page Elements:');
      console.log(`   Loading spinner: ${hasLoadingSpinner}`);
      console.log(`   Error alerts: ${hasErrorAlert}`);
      console.log(`   VM list items: ${hasVMListItems}`);
      console.log(`   Empty state message: ${hasEmptyState}\n`);

      // Get error text if present
      if (hasErrorAlert) {
        const errorText = await page.locator('[class*="MuiAlert"][class*="error"]').textContent();
        console.log(`   ❌ ERROR MESSAGE: ${errorText}\n`);
      }
    } else {
      console.log('❌ Still on login page after 60s - authentication may have failed\n');
    }

    // Print all pirate-flagged console logs
    console.log('\n=== 🏴‍☠️ ALL PIRATE-FLAGGED CONSOLE LOGS ===');
    consoleLogs.filter(log => log.includes('🏴‍☠️')).forEach(log => {
      console.log(log);
    });

    // Print all errors
    console.log('\n=== ❌ ALL ERRORS ===');
    consoleLogs.filter(log => log.includes('[ERROR]') || log.includes('[PAGE ERROR]') || log.includes('[NETWORK FAIL]')).forEach(log => {
      console.log(log);
    });

    console.log('\n⏸️  Browser staying open for 30 seconds for manual inspection...');
    await page.waitForTimeout(30000);

  } catch (error) {
    console.error('❌ Test failed with exception:', error.message);
    console.error(error.stack);
  } finally {
    await browser.close();
    console.log('\n✅ Test complete - check screenshots!');
  }
})();
