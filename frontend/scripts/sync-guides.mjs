// Canonical guides live in /Docs. Commit these generated snapshots so the
// frontend-only Docker build context remains self-contained.
import { copyFile, mkdir, cp } from 'node:fs/promises';
const target = new URL('../src/guide-content/', import.meta.url);
await mkdir(target, { recursive: true });
for (const name of ['APPSEC.md', 'PRODUCT_GUIDE.md', 'KANBAN_SCHEDULER.md', 'ADMIN_GUIDE.md',
  'AI_CLI_MCP.md', 'OPERATIONS.md', 'LOCAL_ARCHITECTURE.md', 'QUICK_START.md']) {
  await copyFile(new URL(`../../Docs/${name}`, import.meta.url), new URL(name, target));
}
const images = new URL('../public/docs/screenshots/', import.meta.url);
await mkdir(images, { recursive: true });
await cp(new URL('../../assets/docs/screenshots/', import.meta.url), images, { recursive: true });
