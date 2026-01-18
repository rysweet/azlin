import { chromium } from 'playwright';

(async () => {
  console.log('🏴‍☠️ Testing MSAL redirect authentication flow...\n');

  const browser = await chromium.launch({
    headless: false,
    slowMo: 500
  });

  const context = await browser.newContext();
  const page = await context.newPage();

  // Capture all logs
  const consoleLogs = [];
  page.on('console', msg => {
    const text = `[${msg.type()}] ${msg.text()}`;
    consoleLogs.push(text);
    if (msg.text().includes('🏴‍☠️') || msg.type() === 'error') {
      console.log(text);
    }
  });

  // Capture API calls
  page.on('response', async response => {
    const url = response.url();
    if (url.includes('management.azure.com')) {
      const status = response.status();
      console.log(`[API] ${status} ${response.request().method()} ${url.substring(0, 100)}...`);

      if (status >= 400) {
        const body = await response.text().catch(() => '');
        console.error(`[API ERROR] ${body.substring(0, 300)}`);
      } else if (url.includes('virtualMachines')) {
        const body = await response.json().catch(() => null);
        if (body?.value) {
          console.log(`[API SUCCESS] ${body.value.length} VMs returned`);
        }
      }
    }
  });

  try {
    console.log('Step 1: Navigate to PWA');
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });
    await page.screenshot({ path: '1-initial.png' });

    console.log('Step 2: Click Sign In (will redirect)');
    await page.getByRole('button', { name: /sign in/i }).click();

    console.log('Step 3: Wait for Microsoft login page...');
    await page.waitForURL(/login\.microsoftonline\.com/, { timeout: 10000 });
    await page.screenshot({ path: '2-microsoft-login.png' });

    console.log('Step 4: Enter credentials');
    console.log('  Entering email...');
    await page.fill('input[type="email"]', 'ryan.sweet@defenderatevet17.onmicrosoft.com');
    await page.click('input[type="submit"]');

    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: '3-after-email.png' });

    console.log('  Entering password...');
    await page.fill('input[type="password"]', '612Gravity!');
    await page.click('input[type="submit"]');

    console.log('Step 5: Handle post-login prompts...');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: '4-after-password.png' });

    // Handle "Stay signed in?" if it appears
    try {
      const staySignedIn = page.getByRole('button', { name: /yes|no/i });
      if (await staySignedIn.count() > 0) {
        console.log('  Clicking "Yes" on stay signed in...');
        await page.getByRole('button', { name: /yes/i }).click();
      }
    } catch (e) {
      console.log('  No stay signed in prompt');
    }

    console.log('Step 6: Wait for redirect back to PWA...');
    await page.waitForURL(/localhost:3000/, { timeout: 15000 });
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: '5-back-to-pwa.png' });

    const finalUrl = page.url();
    console.log(`  Returned to: ${finalUrl}`);

    console.log('Step 7: Navigate to VMs page');
    const hasViewVMs = await page.getByRole('button', { name: /view vms/i }).count() > 0;

    if (hasViewVMs) {
      console.log('  ✅ On dashboard! Clicking View VMs...');
      await page.getByRole('button', { name: /view vms/i }).click();

      await page.waitForTimeout(5000);
      await page.screenshot({ path: '6-vms-page.png', fullPage: true });

      console.log('Step 8: Analyze VMs page');
      const pageText = await page.textContent('body');
      console.log(`  Page content (first 500 chars): ${pageText.substring(0, 500)}`);

      const hasError = await page.locator('[class*="MuiAlert"][class*="error"]').count() > 0;
      const hasEmpty = await page.locator('text=/no vms found/i').count() > 0;
      const vmItems = await page.locator('.MuiListItem-root').count();

      console.log(`  Error alerts: ${hasError}`);
      console.log(`  Empty state: ${hasEmpty}`);
      console.log(`  VM list items: ${vmItems}`);

      if (hasError) {
        const errorText = await page.locator('[class*="MuiAlert"][class*="error"]').textContent();
        console.error(`\n  ❌ ERROR MESSAGE: ${errorText}`);
      }
    } else {
      console.log('  ❌ No View VMs button - still on login?');
    }

    console.log('\n=== 🏴‍☠️ ALL DEBUG LOGS ===');
    consoleLogs.filter(l => l.includes('🏴‍☠️')).forEach(l => console.log(l));

    console.log('\n⏸️  Browser open for 20 seconds for inspection...');
    await page.waitForTimeout(20000);

  } catch (error) {
    console.error(`\n❌ Test failed: ${error.message}`);
    await page.screenshot({ path: 'error-state.png' });
  } finally {
    await browser.close();
    console.log('\n✅ Test complete - check screenshots!');
  }
})();
