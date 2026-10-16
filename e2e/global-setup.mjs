// The API keeps runtime data next to the code. Tests that report outcomes touch two TRACKED files
// (path_states.json, path_history.jsonl): back them up now, restore them in teardown, so a test run
// never leaves the working tree dirty.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const store = path.resolve(here, '../store');
export const TRACKED = ['path_states.json', 'path_history.jsonl', 'path_states_goals.json'];
export const BACKUP = path.join(here, '.store-backup');

export default async function globalSetup() {
  fs.mkdirSync(BACKUP, { recursive: true });
  for (const f of TRACKED) {
    const src = path.join(store, f);
    if (fs.existsSync(src)) fs.copyFileSync(src, path.join(BACKUP, f));
  }
  // Point the (possibly reused) server at the mock provider: deterministic, no API key, no quota.
  const port = process.env.E2E_PORT || 8765;
  if (String(port) !== '8765' && process.env.E2E_FORCE_MOCK !== '1') {
    throw new Error(`E2E_PORT=${port}: this run would switch that server to the mock LLM provider. ` +
      'Set E2E_FORCE_MOCK=1 if that is what you want (never on a server you are using with a real model).');
  }
  const res = await fetch(`http://127.0.0.1:${port}/admin/model`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ provider: 'mock' })
  }).catch(() => null);
  if (!res || !res.ok) console.warn('[e2e] could not switch to the mock provider; the server may be starting');
  // Guard against an accidental paid call: the suite runs only when the server itself says it is on the mock
  // provider. (The webServer is already up when global setup runs, so /health is authoritative.)
  const health = await fetch(`http://127.0.0.1:${port}/health`).then((r) => r.json()).catch(() => null);
  if (!health || health.provider !== 'mock') {
    throw new Error(`E2E refuses to run: the server on :${port} reports provider=${health && health.provider}, ` +
      'not "mock". A live provider would spend paid quota. Stop that server (or set LLM_PROVIDER=mock) and retry.');
  }
}
