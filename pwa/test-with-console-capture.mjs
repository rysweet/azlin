import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: false, slowMo: 300 });
  const context = await browser.newContext();
  const page = await context.newPage();

  const pirateLogs = [];

  page.on('console', msg => {
    const text = msg.text();
    if (text.includes('🏴‍☠️')) {
      pirateLogs.push(text);
      console.log(text);
    }
  });

  console.log('Step 1: Go to PWA\n');
  await page.goto('http://localhost:3000');

  console.log('Step 2: Click Sign In\n');
  await page.click('button:has-text("Sign In")');

  console.log('Step 3: Wait for Microsoft login\n');
  await page.waitForURL(/login\.microsoftonline\.com/, { timeout: 10000 });

  console.log('Step 4: Enter credentials\n');
  await page.fill('input[type="email"]', 'ryan.sweet@defenderatevet17.onmicrosoft.com');
  await page.click('input[type="submit"]');
  await page.waitForLoadState('networkidle');

  await page.fill('input[type="password"]', '612Gravity!');
  await page.click('input[type="submit"]');

  console.log('Step 5: Wait for redirect back (may take time for MFA)\n');
  console.log('(Waiting 90 seconds for MFA/consent...)\n');
  
  try {
    await page.waitForURL(/localhost:3000/, { timeout: 90000 });
    console.log('✅ Redirected back to PWA!\n');
  } catch (e) {
    console.log('Still waiting - check browser for MFA prompt\n');
  }

  await page.waitForTimeout(5000);

  console.log('Step 6: Navigate to VMs\n');
  const url = page.url();
  console.log(`Current URL: ${url}\n`);

  if (url.includes('/dashboard')) {
    await page.click('button:has-text("View VMs")');
  } else {
    await page.goto('http://localhost:3000/vms');
  }

  console.log('Step 7: Wait for diagnostic logs (10 seconds)\n');
  await page.waitForTimeout(10000);

  console.log('\n=== ALL PIRATE LOGS CAPTURED ===\n');
  pirateLogs.forEach(log => console.log(log));

  console.log('\n(Browser staying open 30 seconds)\n');
  await page.waitForTimeout(30000);

  await browser.close();
})();
