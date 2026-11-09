/* Capture real documentation screens from an isolated AIDA smoke stack.
 * Usage: AIDA_UI_URL=... AIDA_SMOKE_USERNAME=... AIDA_SMOKE_PASSWORD=... node scripts/capture_docs.cjs
 * CHROME_PATH may point to an existing Chrome/Chromium executable.
 */
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const path = require('node:path');
const { chromium } = require('playwright');

function base32Decode(value) {
  let bits = 0;
  let buffer = 0;
  const output = [];
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  for (const character of value.replace(/=+$/g, '').toUpperCase()) {
    const index = alphabet.indexOf(character);
    assert.notEqual(index, -1, 'Invalid base32 secret');
    buffer = (buffer << 5) | index;
    bits += 5;
    if (bits >= 8) {
      output.push((buffer >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Buffer.from(output);
}

function totp(secret) {
  const counter = BigInt(Math.floor(Date.now() / 30000));
  const message = Buffer.alloc(8);
  message.writeBigUInt64BE(counter);
  const digest = crypto.createHmac('sha1', base32Decode(secret)).update(message).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const value = (digest.readUInt32BE(offset) & 0x7fffffff) % 1000000;
  return String(value).padStart(6, '0');
}

async function main() {
  const baseUrl = (process.env.AIDA_UI_URL || 'http://localhost:15174').replace(/\/$/, '');
  const username = process.env.AIDA_SMOKE_USERNAME || 'smoke_admin';
  const password = process.env.AIDA_SMOKE_PASSWORD;
  assert.ok(password, 'AIDA_SMOKE_PASSWORD is required');
  const executablePath = process.env.CHROME_PATH ||
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  const outputDir = path.resolve(__dirname, '../../assets/doc');

async function redactText(page, secret, replacement) {
  await page.evaluate(({ value, replacement: replacementText }) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      if (value && node.nodeValue.includes(value)) node.nodeValue = node.nodeValue.replaceAll(value, replacementText);
    }
  }, { value: secret, replacement });
}
  const browser = await chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  try {
    await page.goto(baseUrl, { waitUntil: 'networkidle' });
    await page.getByLabel('Username', { exact: true }).fill(username);
    await page.getByLabel('Password', { exact: true }).fill(password);
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await page.getByRole('heading', { name: 'Dashboard', exact: true }).waitFor();
    await page.screenshot({ path: path.join(outputDir, 'dashboard.png'), fullPage: true });

    await page.goto(`${baseUrl}/settings`, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: 'Security', exact: true }).click();
    await page.getByRole('heading', { name: 'Two-factor authentication (TOTP)', exact: true }).waitFor();
    await page.getByRole('button', { name: 'Set up authenticator', exact: true }).click();
    await page.getByLabel('Current password', { exact: true }).fill(password);
    await page.getByRole('button', { name: 'Generate QR code', exact: true }).click();
    await page.getByText('Manual setup key', { exact: true }).waitFor();
    const secret = (await page.locator('code.break-all').textContent()).trim();
    await redactText(page, secret, 'REDACTED_DEMO_SECRET');
    await page.locator('form div.bg-white svg').first().evaluate((svg) => { svg.style.filter = 'blur(12px)'; });
    await page.screenshot({ path: path.join(outputDir, 'otp-enrollment.png'), fullPage: true });
    await page.getByLabel('Authenticator or recovery code', { exact: true }).fill(totp(secret));
    await page.getByRole('button', { name: 'Enable OTP', exact: true }).click();
    await page.getByText('Save your recovery codes', { exact: true }).waitFor();
    const codes = await page.locator('code').allTextContents();
    const recoveryCode = codes.map((code) => code.trim()).find((code) => code.includes('-'));
    assert.ok(recoveryCode, 'At least one recovery code should be shown once');
    for (const code of codes) await redactText(page, code.trim(), 'XXXX-XXXX-XXXX-XXXX-XXXX');
    await page.screenshot({ path: path.join(outputDir, 'otp-recovery-codes.png'), fullPage: true });
    await page.getByRole('button', { name: 'I saved them', exact: true }).click();
    await page.getByText('Two-factor authentication is enabled. Save these recovery codes now.', { exact: true }).waitFor();
    await page.screenshot({ path: path.join(outputDir, 'otp-security.png'), fullPage: true });

    await page.locator('button[title="Sign out"]:visible').click();
    await page.getByLabel('Username', { exact: true }).fill(username);
    await page.getByLabel('Password', { exact: true }).fill(password);
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await page.getByRole('heading', { name: 'Two-factor authentication', exact: true }).waitFor();
    assert.equal(await page.locator('input[type="password"]').count(), 0);
    await page.screenshot({ path: path.join(outputDir, 'otp-login.png'), fullPage: true });

    await page.getByLabel('Authenticator or recovery code', { exact: true }).fill(recoveryCode);
    await page.getByRole('button', { name: 'Verify and sign in', exact: true }).click();
    await page.getByRole('heading', { name: 'Settings', exact: true }).waitFor();
    await page.goto(`${baseUrl}/users`, { waitUntil: 'networkidle' });
    await page.getByRole('heading', { name: 'Users', exact: true }).waitFor();
    await page.getByText('OTP on', { exact: true }).waitFor();
    await page.screenshot({ path: path.join(outputDir, 'users-otp.png'), fullPage: true });

    assert.deepEqual(pageErrors, []);
    console.log('Captured dashboard, OTP security, OTP challenge, and admin OTP screens');
    console.log('Real UI enrollment + recovery-code login passed; no browser page errors');
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
