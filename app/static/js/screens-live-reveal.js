/* LIVE screens 03 (diagnosis reveal) and 13 (provisional), plus overlays 09 (why drawer) and 11 (do-it-anyway modal).
 * Templates mirror prototype v9; every value comes from the real DiagnosisArtifact. */

/* ── Hypotheses (top-3 explanations, as shares) ────────────────────────────── */
function liveHypotheses() {
  const d = LIVE.artifact || {};
  if (!(d.constraint_map || []).some(c => c.tier !== 'UNKNOWN') && d.primary_constraint) {
    // No scored map (thin evidence): the stated primary constraint is the only explanation we can name.
    return [{ id: d.primary_constraint_id || '', label: brief(userFacing(d.primary_constraint), 96), share: 100, score: d.confidence || 0 }];
  }
  const cm = (d.constraint_map || []).filter(c => c.tier !== 'UNKNOWN')
    .slice().sort((a, b) => (b.effective_score != null ? b.effective_score : b.score) - (a.effective_score != null ? a.effective_score : a.score))
    .slice(0, 3);
  const eff = c => Math.max(0.001, c.effective_score != null ? c.effective_score : c.score);
  const sum = cm.reduce((a, c) => a + eff(c), 0) || 1;
  const sec = (d.secondary_constraints || []).flatMap(splitEnumerated);
  return cm.map((c, i) => ({
    id: c.constraint_id,
    label: i === 0 ? brief(userFacing(d.primary_constraint), 96)
      : brief(userFacing(sec[i - 1] || c.name), 96),
    share: Math.round(eff(c) / sum * 100),
    score: eff(c)
  }));
}
function liveIsProvisional() {
  const d = LIVE.artifact;
  if (!d) return false;
  const h = liveHypotheses();
  const gap = h.length > 1 ? h[0].share - h[1].share : 100;
  return d.status === 'provisional' || d.confidence_band === 'LOW' || gap < 10;
}

/* First sentence of a text, without the verdict emoji/label the engine prefixes to do_not. */
function cleanDoNot(d) {
  const dd = d.do_not_detail || {};
  const text = dd.text || String(d.do_not || '').replace(/^.*?—\s*[^—]*?—\s*/, '');
  return { text: userFacing(text), reason: userFacing(dd.reason || ''), until: userFacing(dd.unlock_condition || dd.until || ''), verdict: dd.verdict || '' };
}
function verdictPillHtml(v) {
  const k = String(v || '').toLowerCase();
  const cls = k === 'stop' ? 'stop' : (k === 'not_yet' ? 'not_yet' : (k === 'test_first' ? 'test_first' : 'open'));
  return `<span class="status-pill ${cls}">${esc(String(v || '').replace('_', ' '))}</span>`;
}
function reasonSecondary(d) {
  const w = (d.why || [])[0] || d.where_you_are || '';
  const t = userFacing(w);
  const first = (t.match(/^[^.!?]+[.!?]/) || [t])[0];
  return { head: brief(first, 92), rest: brief(t.slice(first.length).trim() || d.where_you_are || '', 200) };
}

function screen03Live() {
  const d = LIVE.artifact;
  if (liveIsProvisional() && STORE.forceReveal !== true) return screen13Live();
  const v = liveVerdict();
  const dn = cleanDoNot(d);
  const rs = reasonSecondary(d);
  const nFacts = (LIVE.evidence || []).filter(e => !e.is_gap).length || (d.metrics || {}).n_evidence_total || 0;
  const chips = (LIVE.evidence || []).filter(e => !e.is_gap).slice(0, 2).map(e => `<span class="evidence-chip">${esc(brief(userFacing(e.signal), 34))}</span>`).join('');
  const headline = brief(userFacing(d.primary_constraint), 150);
  const paths = livePathModels();
  const count = k => paths.filter(p => p.status === k).length;
  const tgt = liveGoal().target;
  const glyphKey = { OPEN: 'OPEN', TEST_FIRST: 'TEST_FIRST', NOT_YET: 'NOT_YET', STOP: 'STOP' };
  const pillCls = { OPEN: 'open', TEST_FIRST: 'test_first', NOT_YET: 'not_yet', STOP: 'stop' };
  // Presentation cap (present-cap.js): the reveal lists at most five; the rest is said out loud and opens on the map
  const rpres = presentPaths(paths, { pinned: [useRoadmapStore.getState().activePathId] });
  const pathRows = rpres.visible.map(p => `
            <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;background:${p.status === 'OPEN' ? 'var(--open-soft)' : 'var(--surface-2)'};border-radius:8px">
              <div style="display:flex;align-items:center;gap:10px;min-width:0">
                ${getPathGlyph(glyphKey[p.status])}
                <div style="min-width:0"><div style="font-family:var(--font-ui);font-weight:${p.status === 'OPEN' ? 700 : 600};font-size:14px">${esc(p.name)}</div>
                <div style="font-size:12px;color:var(--ink-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(brief(p.basis, 90))}</div></div>
              </div>
              <span class="status-pill ${pillCls[p.status]}">${STATUS_WORD[p.status]}</span>
            </div>`).join('');
  const tipHtml = LIVE.tips.reveal ? '' : `
      <div class="tip-bubble pointer-left" style="max-width:580px">
        <div style="font-family:var(--font-ui);font-size:12px;font-weight:600;color:var(--on-dark-2);margin-bottom:2px">Tip · shown once</div>
        <div style="font-family:var(--font-ui);font-size:14px;font-weight:700;margin-bottom:4px">Why am I being told no?</div>
        <div style="font-size:12.5px;color:var(--on-dark-3);line-height:1.5;margin-bottom:10px">Stopping a costly move early is often worth more than a new tactic. Every block has a reason and a way to reopen it, and the final call is always yours.</div>
        <button class="btn-secondary btn-sm" style="background:var(--surface);border:none;color:var(--ink)" onclick="dismissTip('reveal')">Got it</button>
      </div>`;
  /* EER §7.3 (audit RV-02/RV-03): the reveal CTA follows the LIVE DECISION — the same source as the
     Next Move card in State (V11_ENGINE.snapshot().nextmove; INV one reality) — not a "start this
     path" button that is always shown. Diagnosis plan steps keep their origin labeled (EER §5.5: sources are not
     merged). PATTERN + copy same as screenState11.moveCta. */
  const nmMove = V11_ENGINE.snapshot().nextmove || null;
  const stepNote = !nmMove ? '' : (nmMove.degraded
    ? 'We could not finish computing the live step. Nothing on your map stopped. It is rebuilt from Talk.'
    : ((nmMove.type === 'QUESTION' || nmMove.type === 'EVIDENCE_REQUEST')
        ? 'One question is the live step right now. Answer it in Talk; this first step follows it.'
        : (nmMove.type === 'HOLD' ? 'The live step is on hold until its checks pass. There is nothing to run yet.' : '')));
  const stepCtaBtn = (label, dest, dark) => `<button class="${dark ? 'btn-primary' : 'btn-secondary'}"${dark ? ' style="background:var(--surface);color:var(--ink);width:100%;margin-top:14px"' : ' style="width:100%;margin-top:14px"'} onclick="goDestination('${dest}')">${label} →</button>`;
  const stepCta = (() => {
    if (!nmMove) return stepCtaBtn('Go to your move', 'moves', true);          /* diagnosis plan: legacy fallback, its route stays Moves */
    if (nmMove.degraded) return stepCtaBtn('Recover in Talk', 'talk', true);   /* technical failure is not a business HOLD (CIR-INV-11) */
    if (nmMove.type === 'ACTION') return stepCtaBtn('Go to your move', 'moves', true);
    if (nmMove.type === 'QUESTION' || nmMove.type === 'EVIDENCE_REQUEST') return stepCtaBtn('Answer it in Talk', 'talk', true);
    if (nmMove.type === 'HOLD') return stepCtaBtn('Explore possible paths', 'maps', false);
    return '';   /* NONE: the engine decided nothing is executed; the CTA is not invented */
  })();

  /* RV-01: reveal = a State-family scene INSIDE the v11 shell (int 02/08 §13 + §19.2: once State exists,
     the five-destination shell is available) — not a full-canvas page with onboarding chrome that cuts off every
     exit path. The hash #/diagnosis/result does not change. */
  const content = `<div class="mp-page">
      <header class="v11-pagehead">
        <div style="display:flex;align-items:center;gap:8px;font-family:var(--font-ui);font-size:13px;margin-bottom:8px;flex-wrap:wrap">
          <span class="section-meta-label">Your diagnosis</span>
          <span>·</span>
          <span style="font-weight:700">${esc(bandWord(d.confidence_band))}</span>
          <span>·</span>
          <a onclick="openDrawer()" style="font-weight:600">Why?</a>
          ${staleBadge()}
          <span>·</span>
          <a onclick="renderScreen('02')" style="font-weight:600">Review the conversation</a>
        </div>
        <h1 class="serif-heading" style="font-size:${headline.length > 92 ? 34 : 42}px">${esc(headline)}</h1>
        <div style="display:flex;align-items:center;gap:12px;margin-top:14px;flex-wrap:wrap">
          <span class="status-pill" style="background:var(--ink);color:var(--on-ink)">${esc(v.pill)}</span>
          <span style="font-size:15px;color:var(--ink-2);font-weight:500">${esc(v.line)}</span>
        </div>
      </header>

      <div class="diag-grid">
        <div class="card-clean" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div class="section-meta-label">What's blocking you</div>
            <h2 style="font-family:var(--font-ui);font-size:18px;font-weight:700;margin-bottom:6px">${esc(rs.head)}</h2>
            <p style="font-size:13.5px;color:var(--ink-2);line-height:1.55">${esc(rs.rest)}</p>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:14px">
            <span class="evidence-chip">Based on: ${nFacts} fact${nFacts === 1 ? '' : 's'}</span>${chips}
          </div>
        </div>

        <div class="card-danger" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div class="section-meta-label" style="color:var(--stop-fg)">What not to do yet</div>
            <h2 style="font-family:var(--font-ui);font-size:18px;font-weight:700;color:var(--stop-fg);margin-bottom:6px">${esc(brief(dn.text, 96) || 'Nothing is blocked right now.')}</h2>
            <p style="font-size:13.5px;color:var(--ink-2);line-height:1.55">${esc(brief(dn.reason || dn.until, 190))}</p>
          </div>
          ${dn.verdict ? `<span style="align-self:flex-start;margin-top:14px">${verdictPillHtml(dn.verdict)}</span>` : ''}
        </div>

        <div class="card-dark" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div class="section-meta-label" style="color:var(--border-strong)">The experiment this picture points to</div>
            <h2 style="font-family:var(--font-ui);font-size:18px;font-weight:700;margin-bottom:6px">${esc(brief(userFacing(d.first_step_today || d.next_best_action), 120))}</h2>
            <p style="font-size:13.5px;color:var(--border);line-height:1.55">${esc(brief(userFacing(d.well_know_when || d.success_metric), 170))}</p>
            ${stepNote ? `<p style="font-size:12.5px;color:var(--border);line-height:1.5;margin:10px 0 0">${esc(stepNote)}</p>` : ''}
          </div>
          ${stepCta}
        </div>
      </div>
      ${tipHtml}

      ${paths.length ? `<div class="card-clean" style="padding:0;overflow:hidden">
        <button style="width:100%;padding:16px 20px;display:flex;align-items:center;justify-content:space-between" onclick="toggleCollapse('collapse-paths')" aria-expanded="false" aria-controls="collapse-paths">
          <div style="text-align:left">
            <div style="font-family:var(--font-ui);font-size:15px;font-weight:700">See ${rpres.overflow ? countWord(rpres.visible.length).toLowerCase() + ' of ' + paths.length + ' paths' : (paths.length === 1 ? 'the path' : (paths.length === 2 ? 'both paths' : 'all ' + paths.length + ' paths'))}${tgt != null ? ' to ' + esc(fmtM(tgt)) + ' a month' : ''}</div>
            <div style="font-size:12.5px;color:var(--ink-2)">${count('OPEN')} open · ${count('TEST_FIRST')} to test · ${count('NOT_YET')} locked for now · ${count('STOP')} stopped</div>
          </div>
          <span>▾</span>
        </button>
        <div style="display:flex;justify-content:flex-end;padding:10px 20px 0">
          <a onclick="goDestination('maps')" style="font-family:var(--font-ui);font-size:13px;font-weight:600;cursor:pointer">View these paths on your map →</a>
        </div>
        <div id="collapse-paths" style="display:none;padding:16px 20px;border-top:1px solid var(--border)">
          <div style="display:flex;flex-direction:column;gap:10px">${pathRows}</div>
          ${livePathOverflowHtml(rpres, { pick: 'openPathOnMap', pickLabel: 'Show on the map' })}
        </div>
      </div>` : liveNoPathsHtml()}

      <div class="card-clean" style="display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap">
        <div>
          <strong>Your map is ready.</strong>
          <div style="font-size:13px;color:var(--ink-2)">Read where you are, explore the possible paths, or keep talking.</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn-secondary" onclick="goDestination('state')">Open State →</button>
          <button class="btn-secondary" onclick="goDestination('maps')">Explore paths →</button>
          <button class="btn-secondary" onclick="goDestination('talk')">Keep talking →</button>
        </div>
      </div>
    </div>`;
  return renderAppShell('state', 'Your diagnosis', content);
}

/* Guard L3 (anti-stale provenance): a diagnosis built by another engine commit must look different. */
function staleBadge() {
  const pv = (LIVE.artifact || {}).provenance || {};
  const stale = pv.code_commit && ENGINE.commit && pv.code_commit !== ENGINE.commit;
  return stale ? `<span>·</span><span class="status-pill stop" title="This diagnosis was built by engine ${esc(pv.code_commit)}; the server now runs ${esc(ENGINE.commit)}. Rebuild it to be sure it matches the current rules.">STALE ENGINE</span>` : '';
}
function dismissTip(k) { LIVE.tips[k] = 1; saveLive(); renderScreen(STORE.currentScreen); }

/* CIR-05 (CI-08): the provisional reason is READ from certification (`certification_reasons`, coded —
 * app/finalization.py), not guessed. "Provisional" = a label of honesty about evidence/freshness/adequacy,
 * NOT "the user ended the interview early" (the old wrong cause). */
function provisionalWhy(d) {
  const rs = d.certification_reasons || [];
  const has = c => rs.indexOf(c) >= 0;
  if (!rs.length) return { because: "This is a first read. It stays open to revision.", lead: "This is a first read of your situation — it stays open to revision. We'd rather tell you that than guess." };
  if (has('CRITICAL_UNKNOWN_OPEN')) return { because: 'Some answers would still change what this says.', lead: "Some answers would still change this picture. We'd rather wait for them than guess." };
  if (has('ELIGIBILITY_STALE') || has('ELIGIBILITY_STATE_CHANGED') || has('ELIGIBILITY_GOAL_CHANGED')) return { because: 'What you told us changed after this was built.', lead: "What you told us since this was built changes the picture. A reassessment brings it up to date." };
  if (has('ELIGIBILITY_CARRIED_OVER')) return { because: 'This read reuses an earlier assessment.', lead: "This read reuses an earlier assessment of your situation. The latest answers can sharpen it." };
  if (has('EVIDENCE_WEAK') || has('EVIDENCE_INSUFFICIENT')) return { because: 'The evidence behind it is still thin.', lead: "We have a leading explanation, but the evidence behind it is still thin. We'd rather tell you that than guess." };
  if (has('ELIGIBILITY_LEVEL_NOT_READY') || has('ELIGIBILITY_ABSENT') || has('ELIGIBILITY_KNOWLEDGE_CHANGED') || has('ELIGIBILITY_CONTRACT_CHANGED')) return { because: 'We are still gathering enough to call it.', lead: "We are still gathering enough to call this one way or another. We'd rather tell you that than guess." };
  return { because: 'This is a first read. It stays open to revision.', lead: "This is a first read of your situation — it stays open to revision. We'd rather tell you that than guess." };
}

/* ── 13 · Provisional diagnosis (top two explanations too close to call) ───── */
function screen13Live() {
  const d = LIVE.artifact;
  const h = liveHypotheses();
  const gap = h.length > 1 ? h[0].share - h[1].share : null;
  const shades = ['var(--ink)', 'var(--ink-3)', 'var(--ink-muted)'];
  const gaps = (LIVE.evidence || []).filter(e => e.is_gap).map(e => userFacing(e.signal)).filter(Boolean);
  const cz = (d.causal_hypothesis || {});
  const asks = (gaps.length ? gaps : [cz.diagnostic_test, ...(cz.still_unproven || [])].filter(Boolean).map(userFacing)).slice(0, 2);
  const dn = cleanDoNot(d);
  const close = gap != null && gap < 10;
  const why = provisionalWhy(d);
  const because = close ? `Right now the top two are only ${gap} point${gap === 1 ? '' : 's'} apart. That's too close to act on.` : why.because;
  const lead = close ? "The top explanations are still close. We'd rather tell you that than guess." : why.lead;
  /* RV-01: same as 03 — provisional reveal is a State-family scene inside the v11 shell;
     the conversation keeps running (EER §6.4: CHECKPOINT → RESULT → TALK CONTINUES). */
  const content = `<div class="mp-page">
      <header class="v11-pagehead">
        <div style="display:flex;align-items:center;gap:8px;font-family:var(--font-ui);font-size:13px;margin-bottom:8px;flex-wrap:wrap">
          <span class="section-meta-label">Your income diagnosis</span>
          <span>·</span>
          <span class="status-pill not_yet" style="background:var(--notyet-bg-2);color:var(--notyet-fg);border:1px solid var(--notyet-border)">NOT FINAL YET</span>
          <span>·</span>
          <a onclick="openDrawer()" style="font-weight:600">Why?</a>
          ${staleBadge()}
          <span>·</span>
          <a onclick="renderScreen('02')" style="font-weight:600">Review the conversation</a>
        </div>
        <h1 class="serif-heading" style="font-size:40px">Here's our best read so far. It isn't certain yet.</h1>
        <p style="font-size:16px;color:var(--ink-2);margin-top:10px;max-width:760px">
          ${esc(lead)}${asks.length ? ` ${asks.length === 1 ? 'One answer' : 'Two answers'} would sharpen it.` : ''}
        </p>
      </header>

      <div class="card-clean">
        <div class="section-meta-label mb-8">${h.length === 1 ? 'The leading explanation' : (close ? `${['Zero', 'One', 'Two', 'Three'][h.length]} explanations, still close` : 'The explanations we considered')}</div>
        <div style="display:flex;flex-direction:column;gap:12px;margin:14px 0">
          ${h.map((x, i) => `
          <div>
            <div style="display:flex;justify-content:space-between;gap:16px;font-size:13.5px;font-weight:600;margin-bottom:4px">
              <span>${i + 1}. ${esc(x.label)}</span>
              <span>${x.share}%</span>
            </div>
            <div style="height:8px;background:var(--surface-2);border-radius:999px;overflow:hidden">
              <div style="width:${x.share}%;height:100%;background:${shades[i] || 'var(--ink-muted)'};border-radius:999px"></div>
            </div>
          </div>`).join('')}
        </div>
        <div style="font-size:12.5px;color:var(--ink-3);line-height:1.5;border-top:1px solid var(--border);padding-top:10px">
          We only name the main problem when one clearly stands out. ${esc(because)}
        </div>
      </div>

      <div class="card-clean" style="max-width:640px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
          <div class="section-meta-label">${asks.length ? 'What would settle it' : 'What happens next'}</div>
        </div>
        ${asks.length ? asks.map((a, i) => `
        <div style="margin-bottom:16px">
          <div style="font-size:14px;font-weight:600;line-height:1.5">${i + 1}. ${esc(brief(a, 200))}</div>
        </div>`).join('') : `<p style="font-size:14px;color:var(--ink-2);line-height:1.55;margin:0 0 16px">A small first step gives us real results to work with. Report what happens and the picture sharpens.</p>`}
        <div style="display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--border);padding-top:14px;gap:12px;flex-wrap:wrap">
          <span style="font-size:12px;color:var(--ink-3)">A follow-up check-in adds these answers to your map.</span>
          <button class="btn-primary" onclick="startFollowUpFlow()">Sharpen my diagnosis →</button>
        </div>
      </div>

      <div class="card-danger">
        <div class="section-meta-label" style="color:var(--stop-fg)">Safe to say already</div>
        <p style="font-size:14px;color:var(--ink);line-height:1.55;margin-top:6px">
          Whichever explanation wins, this still holds: <strong>${esc(brief(dn.text || 'do not spend money or scale anything until a small test has worked.', 240).replace(/[.…]+$/, ''))}.</strong>
          ${dn.reason ? ` ${esc(brief(dn.reason, 200))}` : ''}
        </p>
      </div>

      <div class="card-clean" style="display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap">
        <div>
          <strong>Rather start now?</strong>
          <div style="font-size:13px;color:var(--ink-2)">Begin with a small step that helps under any of these explanations.</div>
        </div>
        <button class="btn-secondary" onclick="goDestination('moves')">Start with a small step →</button>
      </div>

      <div class="card-clean" style="display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap">
        <div>
          <strong>Your map is taking shape.</strong>
          <div style="font-size:13px;color:var(--ink-2)">The possible paths are already drawn. You can look at them while you decide what to answer.</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="btn-secondary" onclick="goDestination('maps')">See your map →</button>
          <button class="btn-secondary" onclick="goDestination('state')">Open State →</button>
        </div>
      </div>
    </div>`;
  return renderAppShell('state', 'Your diagnosis', content);
}

function startFollowUpFlow() {
  liveStartFollowUp();
  renderScreen('02');
}

/* ── 09 · Why? reasoning trace (drawer) ────────────────────────────────────── */
function openDrawer() {
  if (IS_DEMO) return openDrawerDemo();
  const d = LIVE.artifact;
  if (!d) return;
  const facts = (LIVE.evidence || []);
  const real = facts.filter(e => !e.is_gap);
  const gaps = facts.filter(e => e.is_gap);
  const strongRank = { transactional: 4, outcome: 4, behavioral: 3, observed: 2, self_reported: 1 };
  const strongest = real.slice().sort((a, b) => (strongRank[String(b.level).toLowerCase()] || 0) - (strongRank[String(a.level).toLowerCase()] || 0))[0];
  const others = real.filter(e => e !== strongest).slice(0, 4);
  const guesses = (LIVE.tags || []).filter(t => t.kind === 'ASSUMPTION').slice(0, 2);
  const lvl = e => LEVEL_UI[String(e.level || '').toLowerCase()] || LEVEL_UI.self_reported;
  const hyp = liveHypotheses();
  const rd = (d.revenue_state || {}).readiness || {};
  const RD_LABEL = { acquisition: 'Getting clients', conversion: 'Turning talks into deals', delivery: 'Delivering the work', scale: 'Scaling up' };
  const rdTone = v => ({ YES: 'ok', READY: 'ok', PARTIAL: 'warn', CONSTRAINED: 'warn', NO: 'stop', UNKNOWN: 'muted' })[String(v || 'UNKNOWN').toUpperCase()] || 'muted';
  const rdWord = v => ({ YES: 'Ready', READY: 'Ready', PARTIAL: 'Partly ready', CONSTRAINED: 'Held back', NO: 'Not ready', UNKNOWN: 'Not measured' })[String(v || 'UNKNOWN').toUpperCase()] || String(v);
  const dn = cleanDoNot(d);
  const blockedPaths = livePathModels().filter(p => p.status === 'STOP' || p.status === 'NOT_YET');
  const pv = d.provenance || {};
  const stale = pv.code_commit && ENGINE.commit && pv.code_commit !== ENGINE.commit;
  const tone = { ok: 'background:var(--open-soft);color:var(--open-fg)', warn: 'background:var(--notyet-bg);color:var(--notyet-fg)', stop: 'background:var(--stop-bg);color:var(--stop-fg)', muted: 'background:var(--surface-2);color:var(--ink-3)' };
  document.getElementById('drawer-content').innerHTML = `
    <div style="padding:28px 32px 64px;display:flex;flex-direction:column;gap:24px" role="dialog" aria-modal="true" aria-label="Why this diagnosis?">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div class="section-meta-label">Why this diagnosis?</div>
          <h2 class="serif-heading" style="font-size:28px;margin-top:2px">How we reached this diagnosis</h2>
          <p style="font-size:13px;color:var(--ink-2);margin-top:4px">AI reads your answers. Fixed rules do the scoring, so the same answers always give the same result.</p>
        </div>
        <button onclick="closeDrawer()" aria-label="Close" style="font-size:22px;color:var(--ink-3);background:none;border:none;cursor:pointer">✕</button>
      </div>

      <div class="card-clean" style="padding:18px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <span class="section-meta-label">1. What you told us</span>
          <span style="font-family:var(--font-ui);font-size:10.5px;font-weight:700;color:var(--ink-2);background:var(--surface-tint);border:1px solid var(--border);padding:2px 8px;border-radius:4px">Read by AI</span>
        </div>
        ${strongest ? `
        <div style="border:1.5px solid var(--ink);border-radius:8px;padding:12px;background:var(--surface);margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;font-size:12.5px;font-weight:700">
            <span>${esc(brief(userFacing(strongest.signal), 110))}</span>
            <span style="color:var(--open-fg);white-space:nowrap">${esc(lvl(strongest).label)}</span>
          </div>
          ${strongest.source_quote ? `<blockquote style="font-style:italic;font-size:13px;color:var(--ink-2);margin:6px 0">“${esc(brief(strongest.source_quote, 200))}”</blockquote>` : ''}
          <div style="font-size:11px;color:var(--ink-3)">Your words · ${esc((TOPIC_UI[strongest.topic] || {}).label || 'Interview')} · Strongest evidence we have</div>
        </div>` : '<div style="font-size:13px;color:var(--ink-3)">No facts were recorded for this session.</div>'}
        <div style="display:flex;flex-direction:column;gap:8px;font-size:12.5px">
          ${others.map(e => `
          <div style="display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid var(--border)">
            <span>${esc(brief(userFacing(e.signal), 100))}</span>
            <span style="font-weight:700;color:${lvl(e).color};white-space:nowrap">${esc(lvl(e).label)}</span>
          </div>`).join('')}
          ${gaps.slice(0, 2).map(e => `
          <div style="display:flex;justify-content:space-between;gap:12px;padding:6px 0;color:var(--ink-muted)">
            <span>${esc(brief(userFacing(e.signal), 100))}</span><span>Not known yet</span>
          </div>`).join('')}
          ${guesses.map(t => `
          <div style="display:flex;justify-content:space-between;gap:12px;padding:6px 0;color:var(--ink-muted)">
            <span>“${esc(brief(t.quote || t.normalized, 90))}”</span><span>A guess, so not scored</span>
          </div>`).join('')}
        </div>
      </div>

      <div class="card-clean" style="padding:18px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <span class="section-meta-label">2. What could explain it</span>
          <span style="font-family:var(--font-ui);font-size:10.5px;font-weight:700;color:var(--ink-2);background:var(--surface-2);padding:2px 8px;border-radius:4px">Scored by rules</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:10px;margin-top:6px">
          ${hyp.map((x, i) => `
          <div>
            <div style="display:flex;justify-content:space-between;gap:12px;font-size:${i === 0 ? '12.5px' : '12px'};${i === 0 ? 'font-weight:700;' : 'color:var(--ink-3);'}margin-bottom:4px">
              <span>Reason ${i + 1}: ${esc(x.label)}</span>
              <span style="white-space:nowrap">${Math.round(x.score * 100)}% · ${x.share}% share</span>
            </div>
            <div style="height:${i === 0 ? 8 : 6}px;background:var(--surface-2);border-radius:999px;overflow:hidden">
              <div style="width:${x.share}%;height:100%;background:${i === 0 ? 'var(--ink)' : 'var(--ink-muted)'};border-radius:999px"></div>
            </div>
          </div>`).join('') || '<div style="font-size:13px;color:var(--ink-3)">Nothing has been scored yet.</div>'}
        </div>
        <div style="font-size:11.5px;color:var(--ink-3);line-height:1.45;margin-top:12px;border-top:1px solid var(--border);padding-top:8px">
          How scoring works: a payment counts most, something you did counts more than something you said, and guesses never count. Overall confidence: ${Math.round(d.confidence * 100)}% (${esc((d.confidence_band || '').toLowerCase())}).
        </div>
      </div>

      <div class="card-clean" style="padding:18px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <span class="section-meta-label">3. Are you ready to act?</span>
          <span style="font-family:var(--font-ui);font-size:10.5px;font-weight:700;color:var(--ink-2);background:var(--surface-2);padding:2px 8px;border-radius:4px">Checked by rules</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">
          ${Object.keys(RD_LABEL).map(k => `<div style="padding:6px 10px;border-radius:6px;font-weight:600;${tone[rdTone(rd[k])]}">${esc(RD_LABEL[k])}: ${esc(rdWord(rd[k]))}</div>`).join('')}
        </div>
        <div style="margin-top:8px;padding:6px 10px;background:var(--ink);color:var(--on-ink);border-radius:6px;font-weight:700;text-align:center;font-size:12px">Verdict: ${esc(liveVerdict().pill)}</div>
      </div>

      <div class="card-clean" style="padding:18px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <span class="section-meta-label">4. What we blocked, and why</span>
          <span style="font-family:var(--font-ui);font-size:10.5px;font-weight:700;color:var(--ink-2);background:var(--surface-2);padding:2px 8px;border-radius:4px">Based on fixed rules</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:10px;font-size:12.5px">
          ${dn.text ? `<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px"><span>${esc(brief(dn.text, 170))}${dn.reason ? `<br><span style="color:var(--ink-3)">${esc(brief(dn.reason, 200))}</span>` : ''}${dn.until ? `<br><span style="color:var(--ink-3)">Opens when: ${esc(brief(dn.until, 200))}</span>` : ''}</span>${dn.verdict ? verdictPillHtml(dn.verdict) : ''}</div>` : ''}
          ${blockedPaths.map(p => `<div style="display:flex;justify-content:space-between;align-items:center;gap:12px"><span>${esc(p.name)}: ${esc(brief(p.why, 110))}</span><span class="status-pill ${p.status === 'STOP' ? 'stop' : 'not_yet'}">${STATUS_WORD[p.status]}</span></div>`).join('')}
        </div>
      </div>

      <div style="font-size:11.5px;color:var(--ink-3);line-height:1.5">
        Built by engine <b>${esc(pv.code_commit || ENGINE.commit || '?')}</b> · knowledge base <b>${esc(pv.kb_sha256 || '?')}</b>
        ${stale ? '<span class="status-pill stop" style="margin-left:6px">STALE: built by a different engine version</span>' : ''}
      </div>

      <div style="display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--border);padding-top:16px;gap:12px;flex-wrap:wrap">
        <span style="font-size:12px;color:var(--ink-3)">Something wrong here? Add what changed and we'll score it again.</span>
        <button class="btn-secondary btn-sm" onclick="closeDrawer();startFollowUpFlow()">Correct or add something</button>
      </div>
    </div>`;
  document.getElementById('why-drawer').classList.add('open');
  overlayOpened('why-drawer');
}

/* ── 11 · "I want to do this anyway" (modal over the path map) ─────────────── */
function openModal(pathKey) {
  if (IS_DEMO) return openModalDemo();
  const paths = livePathModels();
  const p = paths.find(x => x.key === (pathKey || STORE.modalPath)) || paths.find(x => x.status === 'STOP') || paths[0];
  if (!p) return;
  STORE.modalPath = p.key;
  const d = LIVE.artifact;
  const reason = STORE.adsAppealReason || 'network';
  const choice = STORE.adsActionChoice || 'capped';
  const dn = cleanDoNot(d);
  const notes = {
    network: `<strong style='color:var(--open-fg)'>We'll work around this:</strong> We'll lean on paths that don't depend on messaging people you know, and move the next best test up.`,
    reach: `<strong style='color:var(--ink)'>Why reaching more people can wait:</strong> Reach pays off once people say yes to your offer. Getting a first real result makes everything after it work better.`,
    someone: `<strong style='color:var(--ink)'>Often true, but later:</strong> This tends to work for offers that already sell. We'll bring this path back up once your evidence is stronger.`,
    other: `<strong style='color:var(--ink)'>Tell us in your own words:</strong> Add it in a follow-up check-in, in any language. Your reason becomes evidence, and we'll re-check the map with it.`
  };
  const chip = (k, t) => `<button class="example-chip-box ${reason === k ? 'selected' : ''}" style="${reason === k ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="setAdsAppealReason('${k}')" role="radio" aria-checked="${reason === k}">${t}</button>`;
  const radio = (k, title, text, rec) => `
          <div class="radio-card ${choice === k ? 'selected' : ''}" onclick="setAdsActionChoice('${k}')" role="radio" aria-checked="${choice === k}" tabindex="0" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();setAdsActionChoice('${k}')}">
            <div class="radio-dot"></div>
            <div>
              <div style="display:flex;align-items:center;gap:8px">
                <span style="font-family:var(--font-ui);font-weight:700;font-size:14px">${title}</span>
                ${rec ? '<span class="status-pill open" style="padding:1px 6px;font-size:10px">RECOMMENDED</span>' : ''}
              </div>
              <div style="font-size:12.5px;color:var(--ink-2);margin-top:2px">${text}</div>
            </div>
          </div>`;
  document.getElementById('modal-content').innerHTML = `
    <div role="dialog" aria-modal="true" aria-label="Doing a stopped path anyway" style="display:flex;flex-direction:column;gap:20px;max-height:85vh;overflow-y:auto;padding-right:4px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span class="section-meta-label">${esc(p.name)}</span>
            <span class="status-pill ${p.status === 'STOP' ? 'stop' : (p.status === 'NOT_YET' ? 'not_yet' : (p.status === 'TEST_FIRST' ? 'test_first' : 'open'))}">${STATUS_WORD[p.status]}</span>
          </div>
          <h2 class="serif-heading" style="font-size:28px">You'd like to go this way anyway. It's your call.</h2>
          <p style="font-size:13.5px;color:var(--ink-2);margin-top:4px">Here's what the evidence says, what could go wrong, and a safer way to try it.</p>
        </div>
        <button onclick="closeModal()" aria-label="Close" style="font-size:22px;color:var(--ink-3);background:none;border:none;cursor:pointer">✕</button>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
        <div style="background:var(--surface-2);border-radius:10px;padding:14px">
          <div class="section-meta-label">What we see</div>
          <div style="font-size:13px;color:var(--ink);line-height:1.5;margin-top:4px">${esc(brief(p.why, 200))}</div>
        </div>
        <div style="background:var(--stop-soft);border:1px solid var(--stop-border);border-radius:10px;padding:14px">
          <div class="section-meta-label" style="color:var(--stop-fg)">What could go wrong</div>
          <div style="font-size:13px;color:var(--ink);line-height:1.5;margin-top:4px">${esc(brief(dn.reason || p.why, 200))}</div>
        </div>
      </div>
      <div>
        <div class="section-meta-label mb-8">What's making this appealing right now?</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap" role="radiogroup">
          ${chip('network', "I'd rather not message people I know")}
          ${chip('reach', 'I want to reach more people, faster')}
          ${chip('someone', 'Someone told me it works')}
          ${chip('other', 'Something else')}
        </div>
        <div style="background:var(--surface-2);border-radius:8px;padding:10px 12px;font-size:12.5px;color:var(--ink);line-height:1.5;margin-top:10px">${notes[reason]}</div>
      </div>
      <div>
        <div class="section-meta-label mb-8">What would you like to do?</div>
        <div style="display:flex;flex-direction:column;gap:10px" role="radiogroup">
          ${radio('capped', 'Run a small test instead', 'A small test with a firm limit, once your first step is done. It stops by itself if nothing real comes back before your next check-in.', true)}
          ${radio('full', 'Go ahead with the full plan', "We'll log it as your decision, track the result honestly, and your map will learn from it either way.", false)}
          ${radio('stop', 'Keep it stopped for now', 'Nothing changes. You can come back to this any time.', false)}
        </div>
      </div>
      <div style="display:flex;justify-content:flex-end;gap:10px;border-top:1px solid var(--border);padding-top:14px">
        <button class="btn-secondary btn-sm" onclick="closeModal()">Cancel</button>
        <button class="btn-primary btn-sm" onclick="confirmAdsModalChoice()">Confirm choice →</button>
      </div>
    </div>`;
  document.getElementById('stop-modal').classList.add('open');
  overlayOpened('stop-modal');
}

function confirmAdsModalChoice() {
  if (IS_DEMO) {
    closeModal();
    if (STORE.adsActionChoice === 'capped') alert('Choice saved: a Rp2M test (stops by itself on Day 14) will start once your one-page offer is ready.');
    else if (STORE.adsActionChoice === 'full') alert('Choice saved: running the full Rp10M campaign. We will track the result at your check-in.');
    renderScreen('07');
    return;
  }
  closeModal();
  const choice = STORE.adsActionChoice || 'capped';
  if (choice !== 'stop') {
    LIVE.overrides.push({ path: STORE.modalPath, reason: STORE.adsAppealReason || 'network', choice, ts: Date.now(), cycle: liveTimeline().cycle });
    saveLive();
  }
  const msg = { capped: 'Saved. You will run a small, capped test, and it shows up in your Journey.', full: 'Saved as your decision. We will track the result at your check-in.', stop: 'Nothing changed. This path stays stopped.' }[choice];
  showToast(msg, choice === 'stop' ? '' : 'View journey →', '08');
  renderScreen('07');
}
