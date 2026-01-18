import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9222');
  const page = browser.contexts()[0].pages()[0];

  const consoleLogs = [];

  // Capture console messages
  page.on('console', msg => {
    consoleLogs.push(msg.text());
  });

  console.log('🏴‍☠️ Navigating to /vms page...\n');
  await page.goto('http://localhost:3000/vms', { waitUntil: 'networkidle' });

  console.log('Waiting 8 seconds for diagnostic to complete...\n');
  await page.waitForTimeout(8000);

  console.log('=== ALL CONSOLE OUTPUT ===\n');
  consoleLogs.forEach(log => {
    console.log(log);
  });

  await browser.close();
})();
