/* Small shared helpers (no state). Loaded first. */

/* Demo mode = prototype fixtures (Dimas, 13 cycles) for design review; default = live engine data. */
const QS = new URLSearchParams(location.search);
const IS_DEMO = QS.has('demo');

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/* First sentence(s) of a long engine text, cut at a word boundary. */
function brief(text, max) {
  const t = String(text == null ? '' : text).replace(/\s+/g, ' ').trim();
  if (!t) return '';
  max = max || 140;
  if (t.length <= max) return t;
  // Whole sentences from the start only. A stop counts when whitespace or the end follows it, so "8.5 juta" and
  // "hari ini?')." stay inside their sentence instead of leaving a stray tail ("').") as the whole result.
  let out = '', rest = t;
  for (;;) {
    const m = rest.match(/^(?:[^.!?]|[.!?](?!\s|$))+[.!?]+(?:\s|$)/);
    if (!m) break;
    const next = out ? out + ' ' + m[0].trim() : m[0].trim();
    if (next.length > max) break;
    out = next; rest = rest.slice(m[0].length);
  }
  if (out) return out;
  const cut = t.slice(0, max);
  return cut.slice(0, Math.max(cut.lastIndexOf(' '), Math.floor(max * 0.6))).replace(/[,;:\-–—(]+$/, '') + '…';
}

/* One glance, the rest on demand: { short, more }. short is whole sentences up to max, or (one long sentence) the words up to the
   last clause break before max plus "…"; more is what the reader has not seen yet, "" when the text fits. Nothing is lost:
   the caller shows `more` behind "Read more". */
function gist(text, max) {
  const t = String(text == null ? '' : text).replace(/[ \t]+/g, ' ').replace(/\s*\n\s*/g, '\n').trim();
  if (!t) return { short: '', more: '' };
  const flat = t.replace(/\s*\n\s*/g, ' ');
  max = max || 140;
  if (flat.length <= max) return { short: flat, more: '' };
  let out = '', rest = flat;
  for (;;) {
    const m = rest.match(/^(?:[^.!?]|[.!?](?!\s|$))+[.!?]+(?:\s|$)/);
    if (!m) break;
    const next = out ? out + ' ' + m[0].trim() : m[0].trim();
    if (next.length > (out ? max : max * 1.3)) break;   // a first sentence a little over max still reads better whole
    out = next; rest = rest.slice(m[0].length);
  }
  if (out) return { short: out, more: t };
  const cut = flat.slice(0, max);
  const at = cut.search(/[,;:–—][^,;:–—]*$/);
  const stop = at > max * 0.5 ? at : cut.lastIndexOf(' ');
  return { short: cut.slice(0, stop).replace(/[,;:\-–—(\s]+$/, '') + '…', more: t };
}

/* Engine texts sometimes carry internal doc references or emoji prefixes: keep user copy clean. */
function userFacing(s) {
  return String(s == null ? '' : s)
    .replace(/\s*\([^()]*\bdocs\/[^()]*\)/g, '')
    .replace(/\s*\bdocs\/[0-9A-Za-z._\-/]+(?:\s*§[0-9A-Za-z.\-]+)?/g, '')
    .replace(/\s*\((?:ev-[a-z_]+-\d+[,;\s]*)+\)/g, '')
    .replace(/^[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}️\s]+/u, '')
    .replace(/\s+([.,;:])/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

/* Rp amounts: engine numbers are millions of rupiah ("Rp30M"). */
function fmtM(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  if (Number.isNaN(n)) return null;
  return 'Rp' + (Math.round(n * 10) / 10) + 'M';
}

function lsGet(key, fallback) {
  try { const v = localStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch (e) { return fallback; }
}
function lsSet(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* private mode / quota */ }
}

function timeHM(ts) {
  const d = ts ? new Date(ts) : new Date();
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

function copyText(text) {
  try { if (navigator.clipboard) return navigator.clipboard.writeText(text); } catch (e) { /* ignore */ }
  return Promise.resolve();
}

/* The engine sometimes packs several points into one string: "1) first ... 2) second ... 3) third". */
function splitEnumerated(text) {
  const t = String(text == null ? '' : text).trim();
  if (!/(^|\s)1\)\s/.test(t)) return t ? [t] : [];
  return t.split(/\s*(?:^|\s)\d\)\s+/).map(x => x.trim()).filter(Boolean);
}
