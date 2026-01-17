import { chromium } from 'playwright';

(async () => {
  console.log('🏴‍☠️ Connecting to Chrome and testing VMs page...\n');

  const browser = await chromium.connectOverCDP('http://localhost:9222');
  const page = browser.contexts()[0].pages()[0];

  const allLogs = [];
  page.on('console', msg => {
    const text = msg.text();
    allLogs.push(text);
    if (text.includes('🏴‍☠️')) {
      console.log(text);
    }
  });

  console.log('Current page:', await page.title());
  console.log('Current URL:', page.url(), '\n');

  console.log('Refreshing page to reload with fixed .env...\n');
  await page.reload({ waitUntil: 'networkidle' });

  await page.waitForTimeout(3000);

  console.log('Navigating to /vms...\n');
  await page.goto('http://localhost:3000/vms', { waitUntil: 'networkidle' });

  console.log('Waiting 8 seconds for diagnostic and API call...\n');
  await page.waitForTimeout(8000);

  console.log('=== ALL PIRATE LOGS ===\n');
  allLogs.filter(l => l.includes('🏴‍☠️')).forEach(l => console.log(l));

  console.log('\n=== PAGE CONTENT ===');
  const content = await page.textContent('body');
  console.log(content.substring(0, 500));

  await browser.close();
})();
