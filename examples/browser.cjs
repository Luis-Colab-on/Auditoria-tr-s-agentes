// Runs only inside the isolated Playwright container. Synthetic WordPress only.
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ chromiumSandbox: true });
  const page = await browser.newPage();
  const base = process.env.AUDIT3_BASE_URL;
  const ping = await page.request.get(`${base}/?rest_route=/audit3/v1/ping`);
  assert.equal(ping.status(), 200);
  assert.equal((await ping.json()).synthetic, true);
  await page.goto(`${base}/wp-login.php`);
  await page.locator('#user_login').fill('audit3');
  await page.locator('#user_pass').fill('synthetic-only');
  await page.locator('#wp-submit').click();
  await page.waitForURL('**/wp-admin/**');
  assert.ok(await page.locator('#wpadminbar').isVisible());
  const ajax = await page.request.post(`${base}/wp-admin/admin-ajax.php`, {
    form: { action: 'audit3_echo', _ajax_nonce: 'intentionally-invalid' }
  });
  assert.equal(ajax.status(), 403);
  console.log(JSON.stringify({ synthetic: true, scenarios: ['REST ping', 'admin login form', 'AJAX invalid nonce'], passed: 3 }));
  await browser.close();
})().catch(error => { console.error(error.message); process.exitCode = 1; });
