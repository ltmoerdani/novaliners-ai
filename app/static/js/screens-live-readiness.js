/* LIVE screen 18 (Readiness). The template is the same as the demo (renderReadinessLayout); this file builds its data
 * from ONE server source: GET /session/{sid}/readiness — the adjudicated readiness projection (domains/revenue/
 * projection/readiness.py). The engine has already merged the two views of the same fact (route requirement vs path
 * check), applied "a definite check beats an unknown node", and kept UNKNOWN as UNKNOWN (never silently absent).
 * This file only presents: it maps each item's state to a checklist group and picks the narrative line per section
 * (LLM rewrite when the guard kept it, otherwise the server's deterministic fallback). No state is decided here. */
const RD_BASICS = [['acquisition', 'Getting clients'], ['conversion', 'Turning talks into deals'], ['delivery', 'Delivering the work'], ['scale', 'Scaling up']];
const RD_BASIC_TONE = { YES: 'ok', READY: 'ok', PARTIAL: 'warn', CONSTRAINED: 'warn', NO: 'stop', UNKNOWN: 'muted' };
const RD_BASIC_WORD = { YES: 'Ready', READY: 'Ready', PARTIAL: 'Partly ready', CONSTRAINED: 'Held back', NO: 'Not ready', UNKNOWN: 'Not measured' };

function rdSentence(html) { return html ? html.replace(/[.\s]*$/, '.') : ''; }

/* Plain-language rewrite for one check (LIVE.explain.checks, keyed by the projection's item key — the same keys the
 * server was given). Falls back, check by check, to the server's own wording. */
function rdExplainCheck(ex, key) { return (ex && ex[key]) || null; }

/* An engine sentence with its language marker ({text, lang}) -> safe HTML; a sentence not in the UI language keeps lang="id". */
function rdTxt(o) { return o && o.text ? (o.lang && o.lang !== UI_LANG ? trText(o.text) : esc(o.text)) : ''; }

/* One adjudicated projection item -> a checklist item. Presentation only: the state, the wording of the title and
 * the way to get or check it were all decided by the engine (requirement registry + presentation, or the check's own
 * text); this only lays them out. */
function rdItemOf(it, ex) {
  // an item whose two readings disagree (settled === false) is not confirmed: the engine said so, this only groups it
  const contested = it.settled === false;
  const state = contested ? 'unknown' : (it.state === 'PRESENT' ? 'have' : (it.state === 'UNKNOWN' ? 'unknown' : 'need'));
  const title = rdTxt(it.title);
  const exp = rdExplainCheck(ex, it.key);
  const reason = it.reason && it.reason.text ? rdSentence(rdTxt(it.reason)) : '';
  const how = exp && exp.how ? esc(exp.how) : rdTxt(it.guidance);
  const waits = (it.waits_on || []).map(w => esc(String(w.title || '').replace(/^./, c => c.toLowerCase()))).filter(Boolean);
  let sub = '';
  if (state === 'have') {
    sub = exp && exp.have ? esc(exp.have) : reason;
  } else {
    const lead = state === 'unknown' ? 'To check it: ' : 'To get it: ';
    const note = contested && it.conflict ? rdSentence(rdTxt(it.conflict.note)) : '';
    sub = `${note}${note && reason ? ' ' : ''}${reason}${(note || reason) && how ? ' ' : ''}${how ? lead + how : ''}`;
    if (waits.length) sub += ` Best after ${waits.join(' and ')}.`;
    if (it.executed) sub += ' You said you did this. It counts once results back it up.';
  }
  return { state, partial: !!it.partial, soft: !!it.soft, title, sub, req: it.requirement_id || it.key };
}

function liveReadiness() {
  const d = LIVE.artifact;
  if (!d) return null;
  const ex = liveExplainChecks();
  const exPaths = liveExplainPaths();
  const proj = LIVE.projection;
  // The projection is the authority for status, items and fallbacks. Until it arrives (or if it never
  // does), the shells below stay empty rather than guessing states; livePathModels only names the paths.
  const byKey = {};
  livePathModels().forEach(m => { byKey[m.key] = m; });
  const sources = (proj && proj.paths && proj.paths.length)
    ? proj.paths
    : livePathModels().map(m => ({ key: m.key, status: m.status, basis: { text: m.basis, lang: UI_LANG }, items: [], narrative: {} }));
  const models = sources.map(ps => {
    const m = byKey[ps.key] || {};
    const items = (ps.items || []).map(it => rdItemOf(it, ex));
    const exp = exPaths.find(x => x.key === ps.key);
    const word = f => (exp && String(exp[f] || '').trim()) || '';
    // Same rule as the map's detail card (screen 07): the rewrite stands alone when it exists,
    // the deterministic fallback is composed from the SAME items the checklist shows. Each narrative
    // field falls back on its own. The fallback sentences were built in the projection, on the engine's side.
    const fb = ps.narrative || {};
    const opening = word('opening');
    const supported = word('supported') || String(fb.supported || '');
    const holding = word('holding') || String(fb.holding || '');
    const unclear = word('unclear') || String(fb.unclear || '');
    const lead = word('why') || (ps.basis && ps.basis.text) || '';
    return {
      key: ps.key, name: esc(m.name || ps.key), status: ps.status, basis: esc(lead),
      isActive: !!m.isActive, items,
      opening: esc(opening), supported: esc(supported), holding: esc(holding), unclear: esc(unclear)
    };
  });
  const rd = (d.revenue_state || {}).readiness || {};
  const basics = RD_BASICS.map(([k, label]) => {
    const v = String(rd[k] || 'UNKNOWN').toUpperCase();
    return { label, word: RD_BASIC_WORD[v] || 'Not measured', tone: RD_BASIC_TONE[v] || 'muted' };
  });
  const active = models.find(m => m.isActive);
  const sel = models.find(m => m.key === STORE.readinessPath) ? STORE.readinessPath : (active ? active.key : (models[0] || {}).key);
  return { basics, paths: models, sel };
}

