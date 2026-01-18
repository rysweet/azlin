import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Capture console errors
  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  // Capture page errors
  const pageErrors = [];
  page.on('pageerror', error => {
    pageErrors.push(error.message);
  });

  // Capture failed requests
  const failedRequests = [];
  page.on('requestfailed', request => {
    failedRequests.push({
      url: request.url(),
      failure: request.failure().errorText
    });
  });

  console.log('🏴‍☠️ Navigating to http://localhost:3000...');
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle' });

  console.log('📸 Taking screenshot before clicking...');
  await page.screenshot({ path: 'before-signin.png', fullPage: true });

  console.log('🔍 Looking for Sign In button...');
  const signInButton = page.getByRole('button', { name: /sign in/i });
  const count = await signInButton.count();
  console.log(`   Found ${count} matching button(s)`);

  if (count > 0) {
    console.log('🖱️  Clicking Sign In button...');
    try {
      await signInButton.click();
      console.log('   Button clicked successfully');
    } catch (e) {
      console.log(`   Click failed: ${e.message}`);
    }

    console.log('⏳ Waiting 3 seconds for response...');
    await page.waitForTimeout(3000);

    console.log('📸 Taking screenshot after clicking...');
    await page.screenshot({ path: 'after-signin.png', fullPage: true });
  }

  // Report findings
  console.log('\n=== 🔴 CONSOLE ERRORS ===');
  if (consoleErrors.length === 0) {
    console.log('None');
  } else {
    consoleErrors.forEach((err, i) => {
      console.log(`${i + 1}. ${err}`);
    });
  }

  console.log('\n=== 🔴 PAGE ERRORS ===');
  if (pageErrors.length === 0) {
    console.log('None');
  } else {
    pageErrors.forEach((err, i) => {
      console.log(`${i + 1}. ${err}`);
    });
  }

  console.log('\n=== 🔴 FAILED REQUESTS ===');
  if (failedRequests.length === 0) {
    console.log('None');
  } else {
    failedRequests.forEach((req, i) => {
      console.log(`${i + 1}. ${req.url}`);
      console.log(`   Error: ${req.failure}`);
    });
  }

  // Get any error messages from the page
  console.log('\n=== 📄 PAGE CONTENT ===');
  const bodyText = await page.locator('body').textContent();
  console.log(bodyText.substring(0, 1000));

  // Check for error elements
  const errorElements = await page.locator('[class*="error"], [class*="Error"]').all();
  if (errorElements.length > 0) {
    console.log('\n=== ⚠️  ERROR ELEMENTS FOUND ===');
    for (const el of errorElements) {
      const text = await el.textContent();
      console.log(`- ${text}`);
    }
  }

  await browser.close();
  console.log('\n✅ Test complete. Screenshots saved.');
})();
