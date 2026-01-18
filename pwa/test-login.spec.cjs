const { test, expect } = require('@playwright/test');

test('PWA Login Flow - Capture Sign In Error', async ({ page }) => {
  // Listen for console errors
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  // Listen for page errors
  const pageErrors = [];
  page.on('pageerror', error => {
    pageErrors.push(error.message);
  });

  // Listen for failed requests
  const failedRequests = [];
  page.on('requestfailed', request => {
    failedRequests.push({
      url: request.url(),
      failure: request.failure().errorText
    });
  });

  // Navigate to PWA
  console.log('Navigating to http://localhost:3000...');
  await page.goto('http://localhost:3000');

  // Wait for page to load
  await page.waitForLoadState('networkidle');

  // Take screenshot before clicking
  await page.screenshot({ path: 'before-signin.png' });
  console.log('Screenshot saved: before-signin.png');

  // Find and click Sign In button
  console.log('Looking for Sign In button...');
  const signInButton = page.getByRole('button', { name: /sign in/i });

  // Check if button exists
  const buttonExists = await signInButton.count() > 0;
  console.log(`Sign In button found: ${buttonExists}`);

  if (buttonExists) {
    console.log('Clicking Sign In button...');
    await signInButton.click();

    // Wait a moment for error to occur
    await page.waitForTimeout(2000);

    // Take screenshot after clicking
    await page.screenshot({ path: 'after-signin.png' });
    console.log('Screenshot saved: after-signin.png');
  }

  // Report all errors
  console.log('\n=== CONSOLE ERRORS ===');
  consoleErrors.forEach((err, i) => {
    console.log(`${i + 1}. ${err}`);
  });

  console.log('\n=== PAGE ERRORS ===');
  pageErrors.forEach((err, i) => {
    console.log(`${i + 1}. ${err}`);
  });

  console.log('\n=== FAILED REQUESTS ===');
  failedRequests.forEach((req, i) => {
    console.log(`${i + 1}. ${req.url}`);
    console.log(`   Error: ${req.failure}`);
  });

  // Get page content for debugging
  const pageText = await page.textContent('body');
  console.log('\n=== PAGE CONTENT (first 500 chars) ===');
  console.log(pageText.substring(0, 500));
});
