import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9222');
  const page = browser.contexts()[0].pages()[0];

  console.log('🏴‍☠️ Connected to Chrome - listening to console...');
  console.log('   Current page:', await page.title());
  console.log('   Current URL:', page.url());
  console.log('\n👉 NOW CLICK "VIEW VMs" IN THE BROWSER');
  console.log('   I will capture all console output...\n');
  console.log('=== CONSOLE OUTPUT ===\n');

  // Capture all console messages
  page.on('console', msg => {
    const text = msg.text();
    console.log(text);

    // Highlight pirate logs
    if (text.includes('🏴‍☠️')) {
      console.log('>>> ' + text);
    }
  });

  // Listen for 60 seconds
  await page.waitForTimeout(60000);

  console.log('\n✅ Listening complete');
  await browser.close();
})();
