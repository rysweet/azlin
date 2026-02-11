import { chromium } from 'playwright';

console.log('🎭 Launching headless browser to test PWA...\n');

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

// Collect console messages
const consoleMessages = [];
page.on('console', msg => {
  const text = msg.text();
  consoleMessages.push(`[${msg.type().toUpperCase()}] ${text}`);
});

// Collect network failures
page.on('requestfailed', request => {
  console.log(`❌ Request failed: ${request.url()} - ${request.failure().errorText}`);
});

// Load the PWA
console.log('📡 Loading: https://mango-bush-070e8f80f.6.azurestaticapps.net\n');

try {
  await page.goto('https://mango-bush-070e8f80f.6.azurestaticapps.net', {
    waitUntil: 'networkidle',
    timeout: 30000
  });

  // Wait for React to render
  await page.waitForTimeout(3000);

  const title = await page.title();
  const bodyText = await page.textContent('body');

  console.log(`📄 Page Title: ${title}`);
  console.log(`📄 Page loaded successfully!\n`);

  // Check for specific text
  if (bodyText.includes('Configuration Error')) {
    console.log('❌ FOUND: Configuration Error on page');
    console.log('   (Env vars not embedded properly)\n');
  } else if (bodyText.includes('Loading')) {
    console.log('⏳ Page shows "Loading..."');
    console.log('   (Normal before login)\n');
  } else if (bodyText.includes('Sign in')) {
    console.log('✅ Login page loaded successfully!\n');
  }

  // Show console messages (errors and warnings only)
  console.log('📝 Browser Console (Errors & Warnings):\n');
  const important = consoleMessages.filter(m => m.includes('[ERROR]') || m.includes('[WARNING]'));
  if (important.length > 0) {
    important.forEach(msg => console.log(`   ${msg}`));
  } else {
    console.log('   (No errors or warnings - showing all messages)');
    consoleMessages.slice(-15).forEach(msg => console.log(`   ${msg}`));
  }

} catch (error) {
  console.log(`❌ Error loading page: ${error.message}`);
} finally {
  await browser.close();
}
