/* Capture comprehensive real UI documentation using synthetic demo data only. */
const { chromium } = require('playwright');
const path = require('path');

const baseUrl = process.env.AIDA_UI_URL || 'http://localhost:15174';
const apiUrl = process.env.AIDA_API_URL || 'http://localhost:18001/api';
const outputDir = path.resolve(__dirname, '../../assets/doc');

async function redact(page, secret) {
  await page.evaluate((value) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      if (value && node.nodeValue.includes(value)) node.nodeValue = node.nodeValue.replaceAll(value, 'REDACTED_DEMO_KEY');
    }
  }, secret);
}

async function main() {
  const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: true,
    args: ['--no-sandbox'],
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  const capture = async (name) => {
    await page.screenshot({ path: path.join(outputDir, `${name}.png`), fullPage: true });
    console.log(`captured ${name}.png`);
  };
  try {
    await page.goto(baseUrl, { waitUntil: 'networkidle' });
    await page.getByLabel('Username', { exact: true }).fill(process.env.AIDA_SMOKE_USERNAME || 'codex_e2e');
    await page.getByLabel('Password', { exact: true }).fill(process.env.AIDA_SMOKE_PASSWORD || 'CodexE2E!only');
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await page.getByRole('heading', { name: 'Dashboard', exact: true }).waitFor();
    await page.waitForLoadState('networkidle');
    await capture('dashboard-full');

    const pages = [
      ['/assessments', 'Assessments', 'assessments'],
      ['/assessments/1', 'Demo Web Assessment', 'assessment-detail-full'],
      ['/runs', 'Scan Runs', 'scan-runs'],
      ['/commands', 'Commands', 'commands'],
      ['/board', 'Task Board', 'task-board'],
      ['/takeover', 'Subdomain Takeover', 'subdomain-takeover'],
      ['/users', 'Users', 'users'],
    ];
    for (const [route, text, name] of pages) {
      await page.goto(`${baseUrl}${route}`, { waitUntil: 'networkidle' });
      await page.getByText(text, { exact: true }).first().waitFor();
      await capture(name);
    }

    const tabs = [
      ['General', 'settings-general'],
      ['Tools', 'settings-tools'],
      ['Notifications', 'settings-notifications'],
      ['AI Models', 'settings-ai-models'],
      ['Knowledge', 'settings-knowledge'],
      ['Agents', 'settings-agents'],
      ['Scheduler', 'settings-scheduler'],
      ['Reports', 'settings-reports'],
      ['SSO', 'settings-sso'],
      ['Audit Log', 'settings-audit'],
      ['About', 'settings-about'],
    ];
    await page.goto(`${baseUrl}/settings`, { waitUntil: 'networkidle' });
    for (const [tab, name] of tabs) {
      await page.getByRole('button', { name: tab, exact: true }).click();
      await page.waitForLoadState('networkidle');
      await capture(name);
    }

    await page.getByRole('button', { name: 'MCP Access', exact: true }).click();
    await page.getByText('Enable HTTP MCP transport', { exact: true }).waitFor();
    await page.waitForLoadState('networkidle');
    const enabled = page.getByRole('checkbox');
    if (!(await enabled.isChecked())) {
      await page.locator('label').filter({ has: enabled }).click();
      await page.getByText('HTTP MCP enabled', { exact: true }).waitFor();
    }
    await page.waitForLoadState('networkidle');
    await capture('settings-mcp');
    await page.getByRole('button', { name: 'Create key', exact: true }).click();
    await page.getByPlaceholder('Key name', { exact: true }).fill('Documentation demo — disposable');
    await page.getByRole('button', { name: 'Create', exact: true }).click();
    await page.getByText('Key created', { exact: true }).waitFor();
    const fullKey = (await page.locator('code.break-all').first().textContent()).trim();
    const clients = [
      ['Claude Code', 'mcp-client-claude-code'],
      ['Codex', 'mcp-client-codex'],
      ['Gemini CLI', 'mcp-client-gemini'],
      ['Cursor', 'mcp-client-cursor'],
      ['Claude Desktop', 'mcp-client-claude-desktop'],
      ['Generic MCP', 'mcp-client-generic'],
    ];
    for (const [client, name] of clients) {
      await page.getByRole('button', { name: client, exact: true }).click();
      await redact(page, fullKey);
      await capture(name);
    }
    await page.getByRole('button', { name: 'Done', exact: true }).click();
    const token = await page.evaluate(() => localStorage.getItem('aida_token'));
    const keysResponse = await page.request.get(`${apiUrl}/api-keys`, { headers: { Authorization: `Bearer ${token}` } });
    const keys = await keysResponse.json();
    const demoKey = keys.find((key) => key.name === 'Documentation demo — disposable');
    if (demoKey) {
      const revoked = await page.request.delete(`${apiUrl}/api-keys/${demoKey.id}`, { headers: { Authorization: `Bearer ${token}` } });
      if (!revoked.ok()) throw new Error(`Failed to revoke documentation key: ${revoked.status()}`);
    }
    if (errors.length) throw new Error(`Browser errors: ${errors.join(' | ')}`);
    console.log('Comprehensive documentation capture passed; disposable MCP key revoked');
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
