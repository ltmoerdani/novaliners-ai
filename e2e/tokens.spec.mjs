// Guard for the dark theme: every colour in the UI must be a token (var(--...)), because a hard-coded hex does not
// switch with the theme. Only token definitions (app.css :root blocks, live.css) and the engine widget (always dark) may use hex.
import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.resolve(here, '../app/static');
const HEX = /(?<![&\w#])#[0-9a-fA-F]{6}\b|(?<![&\w#])#[0-9a-fA-F]{3}\b/g;

function offenders(file) {
  const src = fs.readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, m => m.replace(/[^\n]/g, ' '));
  const bad = [];
  src.split('\n').forEach((line, i) => {
    if (/^\s*--[\w-]+\s*:/.test(line)) return;             // a token definition
    if (/^\s*\/\//.test(line)) return;                     // a comment
    const m = line.match(HEX);
    if (m) bad.push(`${path.basename(file)}:${i + 1} ${m.join(' ')}`);
  });
  return bad;
}

test('no hard-coded colours in the UI code (use var(--token) so the dark theme applies)', () => {
  const files = fs.readdirSync(path.join(STATIC, 'js')).filter(f => f.endsWith('.js') && f !== 'widget.js').map(f => path.join(STATIC, 'js', f));
  files.push(path.join(STATIC, 'app.css'), path.join(STATIC, 'index.html'));
  const bad = files.flatMap(offenders);
  expect(bad, bad.slice(0, 20).join('\n')).toEqual([]);
});

// D4 (MVP integration record): the design source is prototype v11, not v9.
const PROTO11 = path.resolve(here, '../../docs/07-design/Prototype Novaliners dengan narrative infographic/Revenue Navigation v11.dc.html');

/* Token definitions of the light theme: the first `:root { ... }` block, plus the `@media ... { :root { ... } }` overrides. */
function rootTokens(src) {
  const out = {};
  // Every top-level :root block counts (the phase-1 workspace tokens live in a second :root in the
  // prototype). First definition wins, matching how the cascade treats later redefinitions of a token.
  for (const m of src.matchAll(/:root\s*\{([\s\S]*?)\n\}/g)) {
    for (const d of m[1].matchAll(/^\s*(--[\w-]+)\s*:\s*([^;]+);/gm)) if (!(d[1] in out)) out[d[1]] = d[2].trim();
  }
  return out;
}
function rootMedia(src) {
  const out = [];
  for (const m of src.matchAll(/@media\s*(\([^)]*\))\s*\{\s*:root\s*\{([^}]*)\}\s*\}/g)) {
    const t = {};
    for (const d of m[2].matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) t[d[1]] = d[2].trim();
    out.push(`${m[1]} ${JSON.stringify(t)}`);
  }
  return out.sort();
}

test('every v11 light token exists in the MVP with the same value', () => {
  const v11 = rootTokens(fs.readFileSync(PROTO11, 'utf8'));
  const mvp = rootTokens(fs.readFileSync(path.join(STATIC, 'app.css'), 'utf8'));
  const diff = Object.keys(v11).filter(k => mvp[k] !== v11[k]).map(k => `${k}: v11 ${v11[k]} · MVP ${mvp[k]}`);
  expect(diff, diff.join('\n')).toEqual([]);
  expect(Object.keys(v11).length, 'the v11 :root block was parsed').toBeGreaterThan(50);
});

test('the v11 responsive token overrides (page margins, type scale) are in the MVP', () => {
  const v11 = rootMedia(fs.readFileSync(PROTO11, 'utf8'));
  const mvp = rootMedia(fs.readFileSync(path.join(STATIC, 'app.css'), 'utf8'));
  expect(v11.length, 'the v11 media overrides were parsed').toBeGreaterThanOrEqual(2);
  expect(v11.filter(x => !mvp.includes(x))).toEqual([]);
});

// Tokens the MVP keeps on top of v11 (record §3, token ledger): the dark theme and the v9 screens that stay as LEGACY
// (D5) use them. Any new MVP-only token has to be added here on purpose.
const MVP_ONLY = new Set([
  '--surface-tint', '--surface-3', '--surface-4', '--on-ink', '--ink-hover', '--ink-2b', '--ink-muted-2',
  '--ink-aa-1', '--ink-aa-2', '--ink-aa-3', '--open-on-ink', '--open-on-ink-2', '--open-line-2', '--notyet-bg-2',
  '--stop-fg-2', '--stop-line-soft', '--violet', '--indigo-fg', '--indigo-bg', '--accent', '--accent-hover',
  '--logo-light', '--logo-dark',
  // recorded 14 Oct 2026 (R6): the prototype refresh (38d9271, design system v1) no longer defines --rail-w; the MVP's
  // .dest-page and rail toggle still use it. A deliberate, recorded divergence until the rail layout is ported.
  '--rail-w',
  // recorded 17 Oct 2026: the Maps 2D map (v12 look) tints its first-cycle band and the Now halo; v11 has no token for either.
  '--map-band', '--halo-1', '--halo-2',
]);
test('the MVP defines no theme token that v11 lacks, except the recorded ones', () => {
  const v11 = new Set(Object.keys(rootTokens(fs.readFileSync(PROTO11, 'utf8'))));
  const mvp = Object.keys(rootTokens(fs.readFileSync(path.join(STATIC, 'app.css'), 'utf8')));
  const extra = mvp.filter(t => !v11.has(t) && !MVP_ONLY.has(t));
  expect(extra).toEqual([]);
});
