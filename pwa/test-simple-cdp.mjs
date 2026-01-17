import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9222');
  const page = browser.contexts()[0].pages()[0];

  console.log('Connected to:', await page.title());
  console.log('URL:', page.url());

  // Navigate to VMs page to trigger diagnostic
  console.log('\nNavigating to /vms...');
  await page.goto('http://localhost:3000/vms', { waitUntil: 'networkidle' });

  console.log('Waiting 5 seconds for diagnostic to run...\n');
  await page.waitForTimeout(5000);

  // Get console logs
  const logs = await page.evaluate(() => {
    return window.__consoleLogs || 'No logs captured';
  });

  console.log('Done - check browser console (F12) for 🏴‍☠️ logs');

  await browser.close();
})();
