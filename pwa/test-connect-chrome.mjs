import { chromium } from 'playwright';

(async () => {
  console.log('🏴‍☠️ Connecting to existing Chrome browser...\n');

  // Connect to Chrome with remote debugging
  const browser = await chromium.connectOverCDP('http://localhost:9222');

  // Get existing contexts
  const contexts = browser.contexts();
  console.log(`Found ${contexts.length} browser contexts`);

  const context = contexts[0];
  const pages = context.pages();
  console.log(`Found ${pages.length} pages`);

  let page;
  if (pages.length > 0) {
    page = pages[0];
  } else {
    page = await context.newPage();
  }

  // Capture pirate logs
  page.on('console', msg => {
    const text = msg.text();
    if (text.includes('🏴‍☠️')) {
      console.log(`>>> ${text}`);
    }
  });

  try {
    console.log('Step 1: Navigate to VMs page');
    await page.goto('http://localhost:3000/vms', { waitUntil: 'networkidle' });

    console.log('Step 2: Wait for diagnostic logs (10 seconds)');
    await page.waitForTimeout(10000);

    console.log('\nStep 3: Check page state');
    const url = page.url();
    const pageText = await page.textContent('body');

    console.log(`  Current URL: ${url}`);
    console.log(`  Page content: ${pageText.substring(0, 400)}`);

    console.log('\nStep 4: Take screenshot');
    await page.screenshot({ path: 'chrome-vms-page.png', fullPage: true });

    console.log('\n✅ Check the console output above for subscription ID comparison!');

  } catch (error) {
    console.error(`Error: ${error.message}`);
  }

  console.log('\n(Browser will remain open - close manually when done)');
})();
