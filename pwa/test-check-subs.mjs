import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Capture ALL console
  page.on('console', msg => {
    console.log(`[CONSOLE] ${msg.text()}`);
  });

  console.log('🏴‍☠️ Direct navigation to /vms to check subscription diagnostic\n');

  await page.goto('http://localhost:3000/vms', { waitUntil: 'networkidle' });

  console.log('Waiting 10 seconds for all diagnostic logs...\n');
  await page.waitForTimeout(10000);

  const text = await page.textContent('body');
  console.log(`\nPage content: ${text.substring(0, 300)}\n`);

  console.log('Browser staying open 30 seconds...');
  await page.waitForTimeout(30000);

  await browser.close();
})();
