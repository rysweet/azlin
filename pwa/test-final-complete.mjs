import { chromium } from 'playwright';

(async () => {
  console.log('🏴‍☠️ Complete automated test with full auth and VMs check\n');

  const browser = await chromium.launch({ headless: false, slowMo: 300 });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Capture pirate-flagged logs
  const pirateLogs = [];
  page.on('console', msg => {
    const text = msg.text();
    if (text.includes('🏴‍☠️')) {
      pirateLogs.push(text);
      console.log(`>>> ${text}`);
    }
  });

  try {
    console.log('Step 1: Go to PWA');
    await page.goto('http://localhost:3000');

    console.log('Step 2: Click Sign In (will redirect)');
    await page.click('button:has-text("Sign In")');

    console.log('Step 3: Wait for Microsoft login page');
    await page.waitForURL(/login\.microsoftonline\.com/, { timeout: 10000 });

    console.log('Step 4: Enter email');
    await page.fill('input[type="email"]', 'ryan.sweet@defenderatevet17.onmicrosoft.com');
    await page.click('input[type="submit"]');
    await page.waitForLoadState('networkidle');

    console.log('Step 5: Enter password');
    await page.fill('input[type="password"]', '612Gravity!');
    await page.click('input[type="submit"]');
    await page.waitForLoadState('networkidle');

    console.log('Step 6: Handle any prompts (MFA/stay signed in)');
    // Try to click "Yes" on stay signed in
    try {
      await page.click('input[value="Yes"]', { timeout: 3000 });
      console.log('  Clicked Yes on stay signed in');
    } catch (e) {
      console.log('  No stay signed in prompt or already handled');
    }

    console.log('Step 7: Wait for redirect back to PWA');
    await page.waitForURL(/localhost:3000/, { timeout: 20000 });
    console.log('  ✅ Back at PWA!');

    // Give time for MSAL to process and save token
    await page.waitForTimeout(3000);

    console.log('Step 8: Check current URL');
    console.log(`  URL: ${page.url()}`);

    console.log('Step 9: Navigate to VMs page');
    const viewVmsButton = page.locator('button:has-text("View VMs")');
    const hasButton = await viewVmsButton.count() > 0;

    if (hasButton) {
      console.log('  ✅ Found View VMs button, clicking...');
      await viewVmsButton.click();
    } else {
      console.log('  Navigating directly to /vms');
      await page.goto('http://localhost:3000/vms');
    }

    console.log('Step 10: Wait for VMs page and diagnostic logs');
    await page.waitForTimeout(8000); // Give time for API calls and logging

    console.log('\n=== 🏴‍☠️ ALL PIRATE LOGS CAPTURED ===');
    pirateLogs.forEach((log, i) => {
      console.log(`${i + 1}. ${log}`);
    });

    console.log('\nStep 11: Check page state');
    const pageText = await page.textContent('body');
    console.log(`Page shows: ${pageText.substring(0, 300)}`);

    console.log('\n⏸️  Browser staying open 30 seconds for inspection...');
    await page.waitForTimeout(30000);

  } catch (error) {
    console.error(`\n❌ Test failed: ${error.message}`);
    await page.screenshot({ path: 'test-error.png' });
  } finally {
    await browser.close();
    console.log('\n✅ Test complete!');
  }
})();
