import { chromium } from 'playwright';

(async () => {
  console.log('🏴‍☠️ Testing with corrected subscription ID\n');

  const browser = await chromium.launch({ headless: false, slowMo: 300 });
  const context = await browser.newContext();
  const page = await context.newPage();

  const logs = [];
  page.on('console', msg => {
    const text = msg.text();
    if (text.includes('🏴‍☠️')) {
      logs.push(text);
      console.log(text);
    }
  });

  page.on('response', async resp => {
    const url = resp.url();
    if (url.includes('virtualMachines')) {
      const status = resp.status();
      console.log(`\n[API CALL] ${status} ${url.substring(0, 100)}`);

      if (status === 200) {
        const data = await resp.json().catch(() => null);
        if (data && data.value) {
          console.log(`\n🎉 SUCCESS! API returned ${data.value.length} VMs!\n`);
        }
      } else {
        const err = await resp.text().catch(() => '');
        console.log(`[ERROR] ${err.substring(0, 200)}`);
      }
    }
  });

  await page.goto('http://localhost:3000');

  console.log('Clicking Sign In...');
  await page.click('button:has-text("Sign In")');

  console.log('Waiting for Microsoft login...');
  await page.waitForURL(/login\.microsoftonline/, { timeout: 10000 });

  console.log('Entering email...');
  await page.fill('input[type="email"]', 'ryan.sweet@defenderatevet17.onmicrosoft.com');
  await page.click('input[type="submit"]');
  await page.waitForLoadState('networkidle');

  console.log('Entering password...');
  await page.fill('input[type="password"]', '612Gravity!');
  await page.click('input[type="submit"]');

  console.log('\nWaiting 90 seconds for MFA and redirect...\n');
  await page.waitForTimeout(90000);

  console.log('Final URL:', page.url());

  console.log('\nNavigating to /vms directly...');
  await page.goto('http://localhost:3000/vms');

  console.log('Waiting 10 seconds for VMs to load...\n');
  await page.waitForTimeout(10000);

  console.log('\n=== PIRATE LOGS ===');
  logs.forEach(l => console.log(l));

  const content = await page.textContent('body');
  console.log('\n=== PAGE CONTENT ===');
  console.log(content.substring(0, 400));

  console.log('\nBrowser open 30 seconds...');
  await page.waitForTimeout(30000);

  await browser.close();
})();
