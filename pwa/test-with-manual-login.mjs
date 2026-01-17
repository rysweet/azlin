import { chromium } from 'playwright';

(async () => {
  console.log('🏴‍☠️ Opening Chrome for manual login...\n');

  // Launch persistent browser (keeps auth between runs)
  const userDataDir = '/tmp/playwright-azlin-manual';
  const browser = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    channel: 'chrome', // Use actual Chrome browser
    viewport: { width: 1400, height: 900 },
  });

  const page = browser.pages()[0] || await browser.newPage();

  // Capture ALL console output
  const allConsoleLogs = [];
  page.on('console', msg => {
    const text = `[${msg.type().toUpperCase()}] ${msg.text()}`;
    allConsoleLogs.push(text);
    console.log(text);
  });

  // Capture errors
  page.on('pageerror', error => {
    const text = `[PAGE ERROR] ${error.message}`;
    allConsoleLogs.push(text);
    console.error(text);
  });

  // Capture failed requests
  page.on('requestfailed', request => {
    const text = `[REQUEST FAILED] ${request.url()} - ${request.failure().errorText}`;
    allConsoleLogs.push(text);
    console.error(text);
  });

  // Capture Azure API calls
  page.on('response', async response => {
    if (response.url().includes('management.azure.com') ||
        response.url().includes('login.microsoftonline.com')) {

      const status = response.status();
      const url = response.url();
      console.log(`[API] ${status} ${response.request().method()} ${url.substring(0, 120)}...`);

      if (status >= 400) {
        try {
          const body = await response.text();
          console.error(`[API ERROR BODY] ${body.substring(0, 500)}`);
        } catch (e) {
          // Can't read body
        }
      }
    }
  });

  console.log('📱 Navigating to http://localhost:3000...\n');
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });

  console.log('⏸️  CHROME BROWSER IS NOW OPEN');
  console.log('👉 Please complete the following steps:');
  console.log('   1. Sign in with Azure (click button and complete popup auth)');
  console.log('   2. After you see the Dashboard, click "View VMs"');
  console.log('   3. Watch this terminal - it will automatically capture console logs');
  console.log('');
  console.log('⏰ Waiting 5 minutes for you to test...\n');

  // Wait 5 minutes for user to login and navigate
  await page.waitForTimeout(300000);

  console.log('\n📸 Taking final screenshot...');
  await page.screenshot({ path: 'final-state.png', fullPage: true });

  // Get final page state
  const finalUrl = page.url();
  const finalContent = await page.textContent('body');

  console.log('\n=== 🏁 FINAL STATE ===');
  console.log(`URL: ${finalUrl}`);
  console.log(`Content preview: ${finalContent.substring(0, 300)}...\n`);

  // Save all console logs to file
  const fs = await import('fs');
  fs.writeFileSync('console-logs.txt', allConsoleLogs.join('\n'));
  console.log('💾 All console logs saved to: console-logs.txt\n');

  console.log('=== 🏴‍☠️ PIRATE-FLAGGED LOGS (Debug Messages) ===');
  const pirateLogs = allConsoleLogs.filter(log => log.includes('🏴‍☠️'));
  if (pirateLogs.length === 0) {
    console.log('(No pirate-flagged logs found)');
  } else {
    pirateLogs.forEach(log => console.log(log));
  }

  console.log('\n=== ❌ ALL ERROR LOGS ===');
  const errorLogs = allConsoleLogs.filter(log =>
    log.includes('[ERROR]') ||
    log.includes('[PAGE ERROR]') ||
    log.includes('[REQUEST FAILED]')
  );
  if (errorLogs.length === 0) {
    console.log('(No errors)');
  } else {
    errorLogs.forEach(log => console.log(log));
  }

  await browser.close();
  console.log('\n✅ Test complete! Check console-logs.txt and final-state.png');
})();
