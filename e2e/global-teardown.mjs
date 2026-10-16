import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { TRACKED, BACKUP } from './global-setup.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const store = path.resolve(here, '../store');

export default async function globalTeardown() {
  for (const f of TRACKED) {
    const b = path.join(BACKUP, f);
    if (fs.existsSync(b)) fs.copyFileSync(b, path.join(store, f));
  }
  fs.rmSync(BACKUP, { recursive: true, force: true });
  // Workspaces created by e2e users (ids start with u_e2e)
  const ws = path.join(store, 'workspaces');
  if (fs.existsSync(ws)) for (const d of fs.readdirSync(ws)) if (d.startsWith('u_e2e')) fs.rmSync(path.join(ws, d), { recursive: true, force: true });
}
