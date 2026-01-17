import { chromium } from 'playwright';

(async () => {
  console.log('🏴‍☠️ Starting full authenticated test with real login...\n');

  const browser = await chromium.launch({
    headless: false,
    slowMo: 100
  });

  const context = await browser.newContext({
    viewport: { width: 1400, height: 900 }
  });

  const page = await context.newPage();

  // Comprehensive logging
  const allLogs = [];

  page.on('console', msg => {
    const text = `[${msg.type()}] ${msg.text()}`;
    allLogs.push(text);
    if (msg.text().includes('🏴‍☠️') || msg.type() === 'error') {
      console.log(text);
    }
  });

  page.on('pageerror', error => {
    const text = `[PAGE ERROR] ${error.message}`;
    allLogs.push(text);
    console.error(text);
  });

  page.on('response', async response => {
    if (response.url().includes('management.azure.com')) {
      const status = response.status();
      const method = response.request().method();
      const url = response.url();

      console.log(`[API] ${status} ${method} ${url.substring(0, 100)}...`);

      if (status >= 400) {
        try {
          const body = await response.text();
          console.error(`[API ERROR] ${body}`);
          allLogs.push(`[API ERROR ${status}] ${body}`);
        } catch (e) {}
      } else if (status === 200) {
        try {
          const body = await response.json();
          if (body.value) {
            console.log(`[API SUCCESS] Returned ${body.value.length} items`);
          }
        } catch (e) {}
      }
    }
  });

  try {
    console.log('Step 1: Navigate to PWA');
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });

    console.log('Step 2: Click Sign In');
    const signInButton = page.getByRole('button', { name: /sign in/i });
    await signInButton.click();

    console.log('Step 3: Wait for popup and handle authentication');

    // Wait for popup to open
    const popupPromise = context.waitForEvent('page');
    const popup = await popupPromise;

    console.log('  Popup opened, waiting for Microsoft login page...');
    await popup.waitForLoadState('networkidle');

    // Enter email
    console.log('  Entering email...');
    await popup.fill('input[type="email"]', 'ryan.sweet@defenderatevet17.onmicrosoft.com');
    await popup.click('input[type="submit"]');

    await popup.waitForLoadState('networkidle');

    // Enter password
    console.log('  Entering password...');
    await popup.fill('input[type="password"]', '612Gravity!');
    await popup.click('input[type="submit"]');

    console.log('  Submitted credentials, waiting for auth to complete...');
    await popup.waitForLoadState('networkidle');

    // Handle "Stay signed in?" prompt if it appears
    try {
      await popup.click('input[type="submit"]', { timeout: 3000 });
      console.log('  Clicked "Yes" on stay signed in');
    } catch (e) {
      console.log('  No "stay signed in" prompt');
    }

    // Wait for popup to close and return to main page
    console.log('  Waiting for redirect back to PWA...');
    await page.waitForTimeout(5000);

    console.log('Step 4: Check if authenticated');
    await page.screenshot({ path: 'after-auth.png' });

    const currentUrl = page.url();
    console.log(`  Current URL: ${currentUrl}`);

    // Look for dashboard
    const hasViewVMs = await page.getByRole('button', { name: /view vms/i }).count() > 0;
    console.log(`  Has "View VMs" button: ${hasViewVMs}`);

    if (hasViewVMs) {
      console.log('Step 5: Navigate to VMs page');
      await page.getByRole('button', { name: /view vms/i }).click();

      console.log('  Waiting for VMs page to load...');
      await page.waitForTimeout(5000);

      await page.screenshot({ path: 'vms-page.png', fullPage: true });

      console.log('Step 6: Analyze VMs page');
      const pageContent = await page.textContent('body');
      console.log(`  Page content: ${pageContent.substring(0, 500)}`);

      const hasError = await page.locator('[class*="MuiAlert-error"]').count() > 0;
      const hasEmpty = await page.locator('text=/no vms found/i').count() > 0;
      const vmCount = await page.locator('.MuiListItem-root').count();

      console.log(`  Error alert: ${hasError}`);
      console.log(`  Empty state: ${hasEmpty}`);
      console.log(`  VM list items: ${vmCount}`);

      if (hasError) {
        const errorText = await page.locator('[class*="MuiAlert-error"]').textContent();
        console.error(`  ERROR MESSAGE: ${errorText}`);
      }
    } else {
      console.log('❌ Still on login page - auth failed');
    }

    console.log('\n=== 🏴‍☠️ DEBUG LOGS ===');
    allLogs.filter(l => l.includes('🏴‍☠️')).forEach(l => console.log(l));

    console.log('\n=== ❌ ERRORS ===');
    allLogs.filter(l => l.includes('ERROR') || l.includes('error')).forEach(l => console.log(l));

    console.log('\n⏸️  Keeping browser open for 30 seconds...');
    await page.waitForTimeout(30000);

  } catch (error) {
    console.error('Test failed:', error.message);
  } finally {
    await browser.close();
    console.log('\n✅ Test complete');
  }
})();
