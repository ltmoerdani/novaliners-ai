/* LIVE screen 02 · Diagnosis chat (real interview loop). Markup and spacing mirror prototype v9 screen02();
 * content comes from LIVE (server transcript, evidence ledger, confidence). */
/* One neutral placeholder: the conversation is not organised by step, so the box never promises a topic. */
const CHAT_PLACEHOLDER = 'Tell us what you can. Real numbers and examples help most...';
const LEVEL_UI = {
  self_reported: { label: 'Your words',        color: 'var(--ink-3)' },
  behavioral:    { label: 'Something you did', color: 'var(--test-line)' },
  transactional: { label: 'Real payment',      color: 'var(--open-line)' },
  outcome:       { label: 'Measured result',   color: 'var(--open-line)' },
  observed:      { label: 'Observed',          color: 'var(--notyet-line)' },
  gap:           { label: 'Still unknown',     color: 'var(--ink-muted)' }
};
let thinkingTimer = null, thinkingStart = 0;

function chatFacts() { return (LIVE.evidence || []).filter(e => !e.is_gap && !e.superseded); }

/* Group the evidence panel by claim ROLE (what kind of statement this is), not by domain topic.
 * Roles come from the semantic layer (so.v1): goal/desire/event/assumption/claim. Gaps get their own
 * "Still to learn" section so "we do not know" stays visible (E1). Superseded evidence (the user
 * corrected it later) is NEVER shown as a current fact — it gets a separate "Corrected" section,
 * clearly labeled, history preserved (Gate A: current understanding must match the canonical graph).
 * Empty groups are simply not rendered. */
function chatEvidenceGroups() {
  const all = LIVE.evidence || [];
  const current = all.filter(e => !e.superseded);
  const corrected = all.filter(e => e.superseded);
  const gaps = current.filter(e => e.is_gap);
  const facts = current.filter(e => !e.is_gap);
  const groups = ROLE_KEYS
    .map(k => ({ k, ui: ROLE_UI[k], items: facts.filter(e => evidenceRole(e) === k) }))
    .filter(g => g.items.length);
  return { groups, gaps, corrected };
}

/* Bold the last question of an engine message (v9 puts the ask in bold). */
function engineHtml(text) {
  const t = String(text || '').trim();
  const q = t.lastIndexOf('?');
  if (q < 0) return esc(t).replace(/\n\n/g, '<br><br>').replace(/\n/g, '<br>');
  const head = t.slice(0, q + 1);
  const cut = Math.max(head.lastIndexOf('. ', q - 1), head.lastIndexOf('\n', q - 1), head.lastIndexOf('! ', q - 1));
  const lead = cut > 0 ? head.slice(0, cut + 1).trim() : '';
  const ask = (cut > 0 ? head.slice(cut + 1) : head).trim();
  const tail = t.slice(q + 1).trim();
  return (lead ? esc(lead) + '<br><br>' : '') + '<strong>' + esc(ask) + '</strong>' + (tail ? ' ' + esc(tail) : '');
}

function chatMsgHtml(m, idx) {
  const when = m.ts ? `<span>· ${esc(timeHM(m.ts))}</span>` : '';
  if (m.role === 'user') {
    return `
    <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
      <div style="display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--ink-3)"><span style="font-weight:600">You</span>${when}</div>
      <div style="background:var(--surface-tint);border-radius:14px;padding:14px 18px;font-size:14px;line-height:1.6;color:var(--ink);max-width:85%;white-space:pre-wrap;overflow-wrap:anywhere">${esc(m.text)}</div>
    </div>`;
  }
  // MC01-2: only the LAST DEGRADED reply offers reasoning-only recovery —
  // the story is already saved; there is no resend instruction.
  const retryable = !!(m.move && m.move.degraded && idx === LIVE.msgs.length - 1 && !LIVE.thinking);
  return `
    <div style="display:flex;flex-direction:column;gap:6px">
      <div style="display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--ink-3)"><span>Novaliners</span>${when}</div>
      ${m.move ? `<div>${moveTagHtml(m.move)}</div>` : ''}
      <div data-engine-text style="font-size:15px;line-height:1.65;color:var(--ink)">${engineHtml(m.text)}</div>
      ${retryable ? `
      <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
        <button class="btn-secondary btn-sm" onclick="liveRetryReasoning()" title="Run the step again from your saved story — no need to resend it">↻ Continue</button>
        <span style="font-size:11.5px;color:var(--ink-muted)">Your story is saved — this only retries the processing.</span>
      </div>` : ''}
    </div>`;
}

function chatThinkingHtml(label) {
  return `
    <div style="display:flex;flex-direction:column;gap:6px" role="status" aria-live="polite">
      <div style="font-size:12px;font-weight:600;color:var(--ink-3)">Novaliners</div>
      <div style="font-size:14px;color:var(--ink-3);display:flex;align-items:center;gap:10px">
        <span class="think-dots" aria-hidden="true"><i></i><i></i><i></i></span>
        <span>${esc(label)} <span id="thinking-elapsed" style="color:var(--ink-muted)">0s</span></span>
      </div>
    </div>`;
}

function chatVerdictHtml() {
  const d = LIVE.artifact;
  const band = (d.confidence_band || 'MEDIUM').toUpperCase();
  const n = chatFacts().length;
  // CIR-05: a stale checkpoint is visibly stale — a post-checkpoint correction invalidates the diagnosis basis;
  // reassess re-synthesizes over the current state (the /reassess endpoint already exists).
  const stale = !!LIVE.checkpointStale;
  const prov = (d.certification_reasons && d.certification_reasons.length)
    ? `<span class="status-pill not_yet" style="margin-left:6px" title="Why this is not final: ${esc(d.certification_reasons.join(', '))}">${d.status === 'final' ? 'FINAL' : 'PROVISIONAL'}</span>` : '';
  return `
    <div class="dark-surface" style="background:var(--ink);color:var(--on-ink);padding:26px 30px;border-radius:16px;display:flex;flex-direction:column;gap:14px;box-shadow:0 8px 24px rgba(0,0,0,0.12);margin-top:8px">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
        <span style="font-family:var(--font-ui);font-size:12px;font-weight:600;color:var(--open-on-ink-2)">Diagnosis · ${esc(band.toLowerCase())} confidence${prov}</span>
        <span style="font-size:12px;color:var(--ink-muted)">Built from ${n} fact${n === 1 ? '' : 's'} you gave us</span>
      </div>
      ${stale ? `
      <div style="background:var(--notyet-bg-2);border:1px solid var(--notyet-border);border-radius:10px;padding:10px 14px;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
        <span style="font-size:13px;color:var(--notyet-fg)">What you told us since then changes this picture.</span>
        <button class="btn-secondary btn-sm" id="reassess-now-btn" aria-busy="${LIVE.reassessing ? 'true' : 'false'}"${LIVE.reassessing ? ' disabled' : ''} style="opacity:${LIVE.reassessing ? '0.6' : '1'};cursor:${LIVE.reassessing ? 'progress' : 'pointer'}" onclick="liveReassessNow()">${LIVE.reassessing ? 'Reassessing…' : 'Reassess now'}</button>
      </div>` : ''}
      <div>
        <h2 style="font-family:var(--font-ui);font-size:20px;font-weight:700;margin:0 0 6px">${esc(brief(userFacing(d.primary_constraint), 120))}</h2>
        <p style="font-size:14px;color:var(--border-strong);line-height:1.6;margin:0">${esc(brief(userFacing((d.why || [])[0] || d.where_you_are), 240))}</p>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding-top:12px;border-top:1px solid var(--ink-hover);margin-top:4px;gap:12px;flex-wrap:wrap">
        <a onclick="resetDiagChatLive()" style="font-size:12.5px;color:var(--ink-muted);cursor:pointer;text-decoration:none;display:flex;align-items:center;gap:6px">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/></svg>
          Start the questions over
        </a>
        <button class="btn-primary" style="background:var(--surface);color:var(--ink);font-weight:700;height:42px;padding:0 22px;font-size:14px" onclick="renderScreen('03')">
          See my results &amp; map →
        </button>
      </div>
    </div>`;
}

function chatReadyHtml(soft) {
  const busy = LIVE.finalizing;
  // int 18 §13.8 (honest card, 16 Oct): disclosure from checkpoint_eligibility —
  // how many critical unknowns (blocking final), how many nonblocking (do not change
  // the decision), and path quality (how many are still TEST_FIRST). Numbers come from the server
  // payload; NO new decision is made in the UI (presentation only, phase C).
  const cp = ((navCurrentMove(LIVE.nav) || {}).checkpoint) || {};
  const crit =cp.critical_count != null ? cp.critical_count : null;
  const nonb = cp.nonblocking_count != null ? cp.nonblocking_count : null;
  const rationale = (cp.rationale || '').trim();
  const paths = (LIVE.nav && LIVE.nav.summary && LIVE.nav.summary.paths) || [];
  const tf = paths.filter(p => p.status === 'TEST_FIRST').length;
  const open = paths.filter(p => p.status === 'OPEN').length;
  const pathWarn = paths.length
    ? (open === 0
        ? `All ${paths.length} possible paths are still <b>TEST FIRST</b> — a diagnosis built now would rest on assumptions, not tested evidence.`
        : `${open} path${open > 1 ? 's are' : ' is'} <b>OPEN</b>, ${tf} still <b>TEST FIRST</b> — building now leans on what is proven so far.`)
    : '';
  const unknownWarn = crit != null
    ? (crit > 0
        ? `<b>${crit} key question${crit > 1 ? 's are' : ' is'} still open</b>${nonb != null ? ` — ${nonb} smaller detail${nonb !== 1 ? 's' : ''} would NOT change the decision` : ''}. Answering it could sharpen the result.`
        : `No decision-changing questions remain open${nonb != null ? ` (${nonb} minor detail${nonb !== 1 ? 's' : ''} set aside)` : ''}.`)
    : '';
  const warn = (unknownWarn || pathWarn || rationale) ? `
        <div style="border-left:3px solid var(--notyet-line);padding:8px 12px;background:var(--notyet-soft);border-radius:0 8px 8px 0;font-size:13px;line-height:1.55;color:var(--border-strong)">
          <div style="font-size:11px;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:4px;color:var(--notyet-fg)">Before you decide</div>
          ${unknownWarn ? `<div style="margin-bottom:4px">${unknownWarn}</div>` : ''}
          ${pathWarn ? `<div style="margin-bottom:4px">${pathWarn}</div>` : ''}
          ${rationale ? `<div style="font-style:italic;opacity:0.85">${esc(rationale)}</div>` : ''}
        </div>` : '';
  return `
    <div class="dark-surface" style="background:var(--ink);color:var(--on-ink);padding:26px 30px;border-radius:16px;display:flex;flex-direction:column;gap:14px;box-shadow:0 8px 24px rgba(0,0,0,0.12);margin-top:8px">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
        <span style="font-family:var(--font-ui);font-size:12px;font-weight:600;color:var(--open-on-ink-2)">${busy ? 'Building your diagnosis…' : 'A first picture is ready'}</span>
        <span style="font-size:12px;color:var(--ink-muted)">${chatFacts().length} facts collected</span>
      </div>
      <div>
        <h2 style="font-family:var(--font-ui);font-size:20px;font-weight:700;margin:0 0 6px">${busy ? 'Building your diagnosis…' : 'There is enough for a first read of your situation.'}</h2>
        <p style="font-size:14px;color:var(--border-strong);line-height:1.6;margin:0">${busy
          ? `<span id="finalize-stage">${esc(LIVE.stage || 'Reading your answers…')}</span> <span id="thinking-elapsed" style="color:var(--ink-muted)">0s</span>. This can take a minute or two.`
          : 'You can build now — or keep talking. Nothing is locked either way.'}</p>
        ${!busy ? warn : ''}
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding-top:12px;border-top:1px solid var(--ink-hover);margin-top:4px;gap:12px;flex-wrap:wrap">
        ${busy
          ? `<a onclick="cancelFinalize()" style="font-size:12.5px;color:var(--ink-muted);cursor:pointer;text-decoration:none">Cancel</a>`
          : `<a onclick="resetDiagChatLive()" style="font-size:12.5px;color:var(--ink-muted);cursor:pointer;text-decoration:none">Start the questions over</a>`}
        <button class="btn-primary" style="background:var(--surface);color:var(--ink);font-weight:700;height:42px;padding:0 22px;font-size:14px;${busy ? 'opacity:0.6;cursor:progress' : ''}" ${busy ? 'disabled' : ''} onclick="finalizeNow()">
          ${busy ? 'Building…' : 'Build my diagnosis →'}
        </button>
      </div>
    </div>`;
}

// MC-07: "Keep talking" button on the exhausted-budget bar — focus the input without a round trip;
// a new budget batch opens automatically on the server once the user sends the next message.
function focusChatInput() {
  const el = document.getElementById('chat-input') || document.querySelector('textarea,input[type="text"]');
  if (el) { el.focus(); }
  const box = document.getElementById('chat-box') || el?.closest('.mp-page,[class*="chat"]');
  if (box) box.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

// int 18 phase C (16 Oct): the stage is NOT yet ready to be given an honest status — NOT a build offer
// (S0 forbids offers when the level is not ready). Passive chip: how many material questions
// remain, and that the user can still build at any time via the small link below.
// MC-07 (18 Oct, owner decision): number source = the monotonic QUESTION BUDGET per batch
// (navigation.question_budget) — opened when the batch starts, drops one by one per
// question presented, NEVER rises/stays flat from engine count oscillation; at 0
// a choice appears: keep going (a new batch opens automatically on the next turn) or build the map.
function chatExploringHtml() {
  const cp = ((navCurrentMove(LIVE.nav) || {}).checkpoint) || {};
  const level = cp.level || '';
  const counts = (LIVE.nav && LIVE.nav.summary && LIVE.nav.summary.counts) || {};
  const qb = (LIVE.nav && LIVE.nav.summary && LIVE.nav.summary.question_budget) || null;
  const open = counts.open_askable || 0;
  // MC-07 fix (18 Okt): the budget counter is the OWNER'S PROMISE to the user — it must
  // render whenever a budget exists and the map is not built yet, REGARDLESS of
  // checkpoint level (previously gated on DISCOVERY_NEEDED/STATE_ONLY, the counter
  // disappeared the moment eligibility rose or the checkpoint block was absent).
  if (qb && Number.isFinite(qb.remaining)) {
    const left = Math.max(0, qb.remaining | 0);
    if (left === 0) {
      // Batch budget exhausted: one clear decision — keep understanding (a new batch opens
      // automatically once the user sends a message) or build the map now (same finalize path).
      return `
    <div style="display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap;margin:12px auto 0;padding:10px 16px;border:1px solid var(--border);border-radius:12px;background:var(--surface-tint);width:fit-content">
      <span style="font-family:var(--font-ui);font-size:12.5px;color:var(--ink-2)">That's ${qb.initial || 'a few'} questions answered — enough for a first read.</span>
      <button class="btn-secondary btn-sm" onclick="focusChatInput()">Keep talking</button>
      <button class="btn-primary btn-sm" onclick="finalizeNow()">Build my map →</button>
    </div>`;
    }
    return `
    <div style="display:flex;align-items:center;gap:8px;margin:10px auto 0;padding:8px 14px;border:1px dashed var(--border);border-radius:999px;font-family:var(--font-ui);font-size:12px;color:var(--ink-3);width:fit-content">
      <span style="width:7px;height:7px;border-radius:50%;background:var(--notyet-line);flex-shrink:0" aria-hidden="true"></span>
      <span>${esc(`Still exploring — ${left} question${left === 1 ? '' : 's'} left in this round.`)}</span>
    </div>`;
  }
  // Fallback lama (tanpa budget di payload — server pra-MC-07): tetap digate level.
  if (level !== 'DISCOVERY_NEEDED' && level !== 'STATE_ONLY') return '';
  const txt = level === 'DISCOVERY_NEEDED'
    ? `Still exploring — ${open || 'a few'} key question${open === 1 ? '' : 's'} left before a first read is worth your time.`
    : 'Still mapping the basics — tell me more and the picture builds itself.';
  return `
    <div style="display:flex;align-items:center;gap:8px;margin:10px auto 0;padding:8px 14px;border:1px dashed var(--border);border-radius:999px;font-family:var(--font-ui);font-size:12px;color:var(--ink-3);width:fit-content">
      <span style="width:7px;height:7px;border-radius:50%;background:var(--notyet-line);flex-shrink:0" aria-hidden="true"></span>
      <span>${esc(txt)}</span>
    </div>`;
}

function chatEvidenceAsideHtml(done) {
  const facts = chatFacts();
  const n = facts.length;
  const d = LIVE.artifact;
  const pct = d ? Math.round(d.confidence * 100) : 0;
  const band = d ? (d.confidence_band || 'MEDIUM') : null;
  const barColor = band === 'LOW' ? 'var(--stop-fg)' : (band === 'HIGH' ? 'var(--open-line)' : 'var(--notyet-line)');
  const counts = ((navCurrentMove(LIVE.nav) || {}).reason || {}).counts || null;
  const horizon = (LIVE.state && LIVE.state.goal && LIVE.state.goal.deadline_days) || null;
  // Role groups + separate "Still to learn" (gaps) and "Corrected" (superseded) sections;
  // every CURRENT fact lands in exactly one group; history stays visible but never as fact.
  const { groups, gaps, corrected } = chatEvidenceGroups();
  return `
      <aside aria-label="What we know so far" style="width:360px;min-width:360px;flex-shrink:0;height:100%;background:var(--surface);border-left:1px solid var(--border);box-shadow:-4px 0 16px rgba(0,0,0,0.03);padding:20px 22px;overflow-y:auto;display:flex;flex-direction:column;gap:18px">
        <div style="display:flex;align-items:flex-start;justify-content:space-between">
          <div style="display:flex;flex-direction:column;gap:5px">
            <span style="font-family:var(--font-ui);font-weight:700;font-size:13px;color:var(--ink)">What we know so far</span>
            ${horizon ? `<div style="display:inline-flex;align-items:center;background:var(--surface-tint);border:1px solid var(--border);border-radius:999px;padding:2px 10px;font-size:11.5px;font-weight:600;color:var(--ink-2);width:fit-content">Timeline: ${horizon} days</div>` : ''}
          </div>
          <button onclick="toggleEvidencePanel()" aria-label="Close summary" style="display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:6px;border:1px solid var(--border);background:var(--surface);cursor:pointer;color:var(--ink-2);box-shadow:0 1px 2px rgba(0,0,0,0.02)" title="Close summary">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="15" y1="3" x2="15" y2="21"/></svg>
          </button>
        </div>
        <p style="margin:0;font-size:12px;line-height:1.5;color:var(--ink-3)">From your answers: what you want, what happened, and what holds today. The questions follow what is still unclear, not these groups.</p>
        <div style="display:flex;flex-direction:column;gap:6px">
          <div style="font-size:12px;font-family:var(--font-ui);display:flex;align-items:center;gap:6px;flex-wrap:wrap">
            <span style="font-weight:600;color:var(--ink)">${n} fact${n === 1 ? '' : 's'} collected</span>
            <span style="color:var(--border-strong)">·</span>
            <span id="nav-counts" style="color:var(--ink-3);font-weight:600">${esc(clarityText(LIVE.nav))}</span>
          </div>
          ${d ? `<div style="display:flex;align-items:center;justify-content:space-between;font-size:11.5px;font-family:var(--font-ui);color:var(--ink-3)">
            <span>Confidence</span>
            <span style="font-weight:700;color:var(--ink)">${pct}% · ${esc(band)}</span>
          </div>
          <div style="height:3px;background:var(--border);border-radius:2px;overflow:hidden">
            <div style="width:${Math.min(100, pct)}%;height:100%;background:${barColor};border-radius:2px;transition:width 0.3s ease"></div>
          </div>` : ''}
        </div>
        <div style="display:flex;flex-direction:column;gap:16px">
          ${groups.length ? groups.map(g => `
          <div>
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
              <div style="display:flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:12px;font-weight:700;color:var(--ink)">
                <span style="width:6px;height:6px;border-radius:50%;background:${g.ui.color};display:inline-block"></span>
                <span>${esc(g.ui.label)}</span>
              </div>
              <span style="font-size:11.5px;color:var(--ink-3)">${g.k === 'claim' ? `${g.items.length} fact${g.items.length === 1 ? '' : 's'}` : g.items.length}</span>
            </div>
            <div style="font-size:11px;color:var(--ink-3);line-height:1.4;margin-bottom:8px">${esc(g.ui.desc)}</div>
            ${g.items.map(e => {
              const lv = LEVEL_UI[String(e.level || '').toLowerCase()] || LEVEL_UI.self_reported;
              return `<div class="card-clean" style="padding:10px 12px;margin-bottom:8px">
                <div style="font-size:12.5px;font-weight:600;color:var(--ink)">${esc(brief(userFacing(e.signal), 150))}</div>
                <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
                  <span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:500;color:${lv.color}">
                    <span style="width:5px;height:5px;border-radius:50%;background:${lv.color};display:inline-block"></span> ${esc(lv.label)}
                  </span>
                  ${e._msg != null ? `<a onclick="jumpToChatMsg(${e._msg})" style="font-size:10.5px;color:var(--ink-muted);cursor:pointer;text-decoration:none" title="Jump to the answer this came from">↗ jump</a>` : ''}
                </div>
              </div>`;
            }).join('')}
          </div>`).join('') : '<div style="font-size:12.5px;color:var(--ink-muted);line-height:1.5">Nothing yet. Facts show up here as you answer.</div>'}
          ${gaps.length ? `
          <div style="border-top:1px dashed var(--border-strong);padding-top:14px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
              <div style="display:flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:12px;font-weight:700;color:var(--ink-3)">
                <span style="width:6px;height:6px;border-radius:50%;background:${GAP_UI.color};display:inline-block"></span>
                <span>${esc(GAP_UI.label)}</span>
              </div>
              <span style="font-size:11.5px;color:var(--ink-3)">${gaps.length}</span>
            </div>
            <div style="font-size:11px;color:var(--ink-3);line-height:1.4;margin-bottom:8px">${esc(GAP_UI.desc)}</div>
            ${gaps.map(e => `
            <div class="card-clean" style="padding:10px 12px;margin-bottom:8px;border-style:dashed">
              <div style="font-size:12.5px;font-weight:600;color:var(--ink-2)">${esc(brief(userFacing(e.signal), 150))}</div>
              <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
                <span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:500;color:var(--ink-muted)">
                  <span style="width:5px;height:5px;border-radius:50%;background:var(--ink-muted);display:inline-block"></span> Not known yet
                </span>
                ${e._msg != null ? `<a onclick="jumpToChatMsg(${e._msg})" style="font-size:10.5px;color:var(--ink-muted);cursor:pointer;text-decoration:none" title="Jump to the answer this came from">↗ jump</a>` : ''}
              </div>
            </div>`).join('')}
          </div>` : ''}
          ${corrected.length ? `
          <div style="border-top:1px dashed var(--border-strong);padding-top:14px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
              <div style="display:flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:12px;font-weight:700;color:var(--ink-muted)">
                <span style="width:6px;height:6px;border-radius:50%;background:var(--border-strong);display:inline-block"></span>
                <span>Corrected</span>
              </div>
              <span style="font-size:11.5px;color:var(--ink-3)">${corrected.length}</span>
            </div>
            <div style="font-size:11px;color:var(--ink-3);line-height:1.4;margin-bottom:8px">Things you said before and later corrected. Kept for the record — not part of what we know now.</div>
            ${corrected.map(e => `
            <div class="card-clean" style="padding:10px 12px;margin-bottom:8px;border-style:dashed;opacity:0.75">
              <div style="font-size:12.5px;font-weight:600;color:var(--ink-3)">${esc(brief(userFacing(e.signal), 150))}</div>
              <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
                <span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:500;color:var(--ink-muted)">
                  <span style="width:5px;height:5px;border-radius:50%;background:var(--border-strong);display:inline-block"></span> Previously stated
                </span>
                ${e._msg != null ? `<a onclick="jumpToChatMsg(${e._msg})" style="font-size:10.5px;color:var(--ink-muted);cursor:pointer;text-decoration:none" title="Jump to the answer this came from">↗ jump</a>` : ''}
              </div>
            </div>`).join('')}
          </div>` : ''}
        </div>
      </aside>`;
}

function screen02Live() {
  const panelOpen = !!STORE.chatEvidenceOpen;
  const done = !!LIVE.artifact;
  const facts = chatFacts().length;
  const maxW = panelOpen ? '780px' : '860px';
  // CIR-05 (int 19 §14.4): typing permission is determined by real interaction capability and server
  // authority (409/422/403 from the server refuse), NOT by `interview_done`/artifact presence — a checkpoint is
  // a revisable point, the conversation stays alive (int 18 phase C). In-flight operations (thinking/finalizing) still
  // disable input briefly.
  const canType = !LIVE.thinking && !LIVE.finalizing;
  const busyInput = LIVE.thinking || LIVE.finalizing;
  // CIR-05: the "first picture ready" offer is read from PARALLEL adequacy (checkpoint_eligibility,
  // int 18), not from the ACTION step type — useful questions and the checkpoint offer live together.
  // MC01-5 (audit P1): the ACTION=ready fallback is REMOVED — ACTION measures information not yet known
  // and does NOT automatically mean enough evidence for a diagnosis (dsc.v1: eligibility is the only basis for the offer).
  const cpOffer = !!(((navCurrentMove(LIVE.nav) || {}).checkpoint || {}).can_offer_checkpoint);
  const ready = cpOffer;
  const pillText = done ? 'Diagnosis built' : clarityText(LIVE.nav);
  const pillDot = done || ready ? 'var(--open-line)' : 'var(--notyet-line)';

  const errHtml = LIVE.err ? `
    <div role="alert" style="background:var(--stop-soft);border:1px solid var(--stop-border);border-radius:12px;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:13px;color:var(--stop-fg)">
      <span>${esc(LIVE.err)}</span>
      ${LIVE.failedText ? `<button class="btn-secondary btn-sm" onclick="retryFailedMessage()">Try again</button>` : ''}
    </div>` : '';

  const body = LIVE.msgs.map(chatMsgHtml).join('')
    + (LIVE.thinking ? chatThinkingHtml('Thinking about your answer…') : '')
    + errHtml
    + (done ? chatVerdictHtml() : (ready && !LIVE.thinking ? chatReadyHtml(true) : (!LIVE.thinking && !done ? chatExploringHtml() : '')));

  return `
  <div class="full-canvas" style="height:100%;max-height:100%;background:var(--surface);display:flex;flex-direction:column;overflow:hidden;position:relative;border-radius:12px;border:1px solid var(--border)">
    <div style="flex:1;min-height:0;display:flex;position:relative;overflow:hidden;background:var(--surface);width:100%">
      <div style="flex:1;min-height:0;display:flex;flex-direction:column;align-items:center;position:relative;overflow:hidden;transition: background-color 0.2s, border-color 0.2s, color 0.2s, box-shadow 0.2s, opacity 0.2s, transform 0.2s">

        <div style="width:100%;height:52px;background:var(--surface);z-index:10;flex-shrink:0;border-bottom:1px solid var(--border-subtle);padding:0 32px;display:flex;align-items:center">
          <div style="max-width:${maxW};margin:0 auto;width:100%;display:flex;align-items:center;justify-content:space-between;transition:max-width 0.2s ease">
            <div style="display:flex;align-items:center;gap:10px">
              <a onclick="${LIVE.pendingPrior ? 'abortFollowUp()' : `renderScreen('${LIVE.artifact ? '17' : '01'}')`}" style="display:inline-flex;align-items:center;gap:5px;font-family:var(--font-ui);font-size:12.5px;font-weight:600;color:var(--ink-3);text-decoration:none;cursor:pointer;padding:4px 8px;border-radius:6px;transition: background-color 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s, opacity 0.15s, transform 0.15s" onmouseover="this.style.color='var(--ink)';this.style.background='var(--surface-tint)'" onmouseout="this.style.color='var(--ink-3)';this.style.background='transparent'" title="${LIVE.artifact ? 'Back to your diagnosis' : 'Back'}">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
                <span>${LIVE.artifact || LIVE.pendingPrior ? 'State' : 'Back'}</span>
              </a>
              <span style="color:var(--border);font-size:13px">/</span>
              <div id="nav-pill" style="display:inline-flex;align-items:center;gap:7px;padding:3px 10px 3px 9px;border-radius:999px;background:var(--surface-3);border:1px solid var(--border);margin-left:4px" title="Where this conversation stands, from what you have told us">
                <span style="width:7px;height:7px;border-radius:50%;background:${pillDot};flex-shrink:0" aria-hidden="true"></span>
                <span style="font-family:var(--font-ui);font-size:11.5px;font-weight:600;color:var(--ink-2)">${esc(pillText)}</span>
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <button onclick="resetDiagChatLive()" aria-label="Start the questions over" style="display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;padding:0;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--ink-2);cursor:pointer;box-shadow:0 1px 2px rgba(0,0,0,0.02);transition: background-color 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s, opacity 0.15s, transform 0.15s" onmouseover="this.style.background='var(--surface-tint)';this.style.color='var(--ink)'" onmouseout="this.style.background='var(--surface)';this.style.color='var(--ink-2)'" title="Start the questions over">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
              </button>
              ${!panelOpen ? `
              <button class="btn-secondary btn-sm" onclick="toggleEvidencePanel()" style="display:inline-flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:12px;font-weight:500;color:var(--ink-2b);background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:0 10px;height:28px;cursor:pointer;white-space:nowrap;transition:background 0.15s" onmouseover="this.style.background='var(--surface-tint)'" onmouseout="this.style.background='var(--surface)'" title="Open summary">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
                <span><span class="hide-sm">What we know · </span>${facts}</span>
              </button>` : ''}
            </div>
          </div>
        </div>

        <div id="chat-messages-container" role="log" aria-live="polite" aria-label="Conversation" tabindex="0" style="flex:1;min-height:0;width:100%;display:flex;justify-content:center;overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--border-strong) transparent;padding:28px 32px 24px">
          <div style="width:100%;max-width:${maxW};display:flex;flex-direction:column;gap:24px;transition:max-width 0.2s ease">
            ${body}
          </div>
        </div>

        ${canType ? `
        <div style="width:100%;background:var(--surface);border-top:1px solid var(--border-subtle);flex-shrink:0;padding:10px 32px 18px;display:flex;justify-content:center;z-index:10">
          <div style="width:100%;max-width:${maxW};display:flex;flex-direction:column;gap:8px;transition:max-width 0.2s ease">
            <div id="nav-focus" style="width:100%;text-align:left;padding:10px 14px;border:1px dashed var(--border-strong);border-radius:10px;background:var(--surface);display:flex;flex-direction:column;gap:3px">
              ${moveFocusHtml(LIVE.nav)}
            </div>
            <div style="background:var(--surface);border:1px solid var(--border-strong);border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,0.03);display:flex;flex-direction:column;padding:2px">
              <textarea id="diag-chat-input" rows="2" aria-label="Your answer" placeholder="${esc(CHAT_PLACEHOLDER)}" ${busyInput ? 'disabled' : ''} style="border:none;outline:none;resize:none;background:transparent;color:var(--ink);font-family:var(--font-ui);font-size:14px;line-height:1.5;padding:10px 14px 6px;border-radius:10px" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendDiagChatLive();}">${esc(LIVE.failedText && LIVE.err ? LIVE.failedText : '')}</textarea>
              <div style="display:flex;align-items:center;justify-content:space-between;padding:2px 12px 8px 14px">
                <span style="font-size:11.5px;color:var(--ink-muted);font-family:var(--font-ui);display:flex;align-items:center;gap:6px">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  Use real numbers where you can
                </span>
                <button class="btn-primary" ${busyInput ? 'disabled' : ''} style="width:32px;height:32px;border-radius:50%;padding:0;display:flex;align-items:center;justify-content:center;cursor:pointer;${busyInput ? 'opacity:0.5' : ''}" onclick="sendDiagChatLive()" aria-label="Send answer" title="Send answer">↑</button>
              </div>
            </div>
            ${LIVE.msgs.filter(m => m.role === 'user').length >= 2 ? `
            <div style="text-align:center"><a onclick="finalizeEarly()" style="font-family:var(--font-ui);font-size:12px;font-weight:600;color:var(--ink-3);cursor:pointer" role="button" tabindex="0" onkeydown="if(event.key==='Enter')finalizeEarly()">Enough answers? Build my diagnosis now</a></div>` : ''}
          </div>
        </div>` : ''}
      </div>
      ${panelOpen ? chatEvidenceAsideHtml(done) : ''}
    </div>
  </div>`;
}

/* Re-render the chat only if it is on screen; keep the typing box and scroll position sane. */
function renderChatLive() {
  if (STORE.currentScreen !== '02') return;
  const prevInput = document.getElementById('diag-chat-input');
  const draft = prevInput ? prevInput.value : '';
  renderScreen('02');
  const input = document.getElementById('diag-chat-input');
  if (input && draft && !LIVE.err) input.value = draft;
  const box = document.getElementById('chat-messages-container');
  if (box) box.scrollTop = box.scrollHeight;
  syncThinkingTimer();
}
function syncThinkingTimer() {
  const on = LIVE.thinking || LIVE.finalizing;
  if (on && !thinkingTimer) {
    thinkingStart = Date.now();
    thinkingTimer = setInterval(() => {
      const el = document.getElementById('thinking-elapsed');
      if (el) el.textContent = Math.floor((Date.now() - thinkingStart) / 1000) + 's';
      else { clearInterval(thinkingTimer); thinkingTimer = null; }
    }, 1000);
  } else if (!on && thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
}
function updateFinalizeStage() {
  const el = document.getElementById('finalize-stage');
  if (el) el.textContent = LIVE.stage;
}

function toggleEvidencePanel() {
  STORE.chatEvidenceOpen = !STORE.chatEvidenceOpen;
  if (STORE.currentScreen === 'talk') { renderScreen('talk'); return; }   // the Talk destination has the same panel
  if (IS_DEMO) renderScreen('02'); else renderChatLive();
}
/* The side panel of Talk: your paths, or what is on record */
function setChatPanelTab(tab) {
  STORE.chatPanelTab = tab === 'facts' ? 'facts' : 'map';
  renderScreen(STORE.currentScreen);
}
function jumpToChatMsg(i) {
  const box = document.getElementById('chat-messages-container');
  if (!box) return;
  const rows = box.firstElementChild ? box.firstElementChild.children : [];
  const el = rows[Math.min(i, rows.length - 1)];
  if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' });
}

async function sendDiagChatLive() {
  const input = document.getElementById('diag-chat-input');
  const text = input ? input.value.trim() : '';
  if (!text || LIVE.thinking) { if (input) input.focus(); return; }
  LIVE.failedText = '';
  input.value = '';   // clear first: renderChatLive() restores unsent drafts, and this one is being sent
  const ok = await liveSendMessage(text);
  renderChatLive();
  if (!ok) { const i = document.getElementById('diag-chat-input'); if (i) i.focus(); }
}
/* Leaving an unstarted follow-up cycle: go back to the map that was open before. */
async function abortFollowUp() {
  const sid = LIVE.pendingPrior;
  LIVE.pendingPrior = ''; LIVE.err = ''; LIVE.failedText = '';
  try { if (sid) await liveLoadSession(sid); } catch (e) { /* fall through to whatever is loaded */ }
  renderScreen(LIVE.artifact ? '17' : '01');
}
function finalizeEarly() {
  if (!window.confirm('Build the diagnosis now? It will use only what you have told us so far, so it may be less certain.')) return;
  // CIR-05: there is NO optimistic `interviewDone=true` here — the "done" status comes only from the server
  // after synthesis has actually succeeded (liveFinalize); a synthesis failure leaves the conversation
  // open and input alive (no fake lock).
  finalizeNow();
}
async function retryFailedMessage() {
  const t = LIVE.failedText;
  LIVE.err = ''; LIVE.failedText = '';
  // The failed attempt's user bubble is already in the log: drop it so the retry does not duplicate it.
  if (LIVE.msgs.length && LIVE.msgs[LIVE.msgs.length - 1].role === 'user' && LIVE.msgs[LIVE.msgs.length - 1].text === t) LIVE.msgs.pop();
  if (t) { await liveSendMessage(t); renderChatLive(); }
}
async function finalizeNow() {
  const ok = await liveFinalize();
  if (STORE.currentScreen === '02') renderChatLive();
  if (ok) renderScreen('03');
}
/* The pending state of the legacy "Reassess now" control (the diagnosis card, not the Maps cycle). */
function liveReassessButton(busy) {
  const b = document.getElementById('reassess-now-btn');
  if (!b) return;
  b.disabled = !!busy;
  b.setAttribute('aria-busy', busy ? 'true' : 'false');
  b.textContent = busy ? 'Reassessing…' : 'Reassess now';
  b.style.opacity = busy ? '0.6' : '1';
  b.style.cursor = busy ? 'progress' : 'pointer';
}
/* CIR-05: reassess = re-synthesize over the CURRENT state (the endpoint is expensive and is triggered
   here only by an explicit click). NC-R9: one synthesis at a time, an honest pending label, and the
   redraw only after an ACCEPTED checkpoint — through the version-consistent refresh boundary. */
async function liveReassessNow() {
  if (!LIVE.sid || LIVE.finalizing || LIVE.reassessing) return;
  const sid = LIVE.sid;
  LIVE.reassessing = true;
  liveReassessButton(true);
  try {
    const r = await API.reassess(sid);
    if (LIVE.sid !== sid) return;
    const cp = (r && r.checkpoint) || null;
    if (!r || r.committed !== true || !cp || !cp.checkpoint_id) {
      /* a 200 that accepted no checkpoint is not a success */
      showToast('The reassessment did not return an accepted checkpoint, so nothing is shown as updated.', '', '', 'error');
      return;
    }
    LIVE.checkpointStale = false;
    saveLive();
    /* Two honest shapes: liveRefreshAfterReassessment resolves { ok, exp }; the older
       liveRefreshAfterMutation resolves a boolean. Normalise before judging, never truthy-test an object. */
    let refreshed = false;
    try {
      if (typeof liveRefreshAfterReassessment === 'function') {
        const res = await liveRefreshAfterReassessment({ expectCheckpointId: cp.checkpoint_id, render: false });
        refreshed = !!(res && res.ok === true);
      } else {
        refreshed = (await liveRefreshAfterMutation({ render: false })) === true;
      }
    } catch (e) { refreshed = false; }
    if (!refreshed) {
      showToast('The reassessment was accepted, but the workspace could not be refreshed. Your record is saved — try again shortly.', '', '', 'error');
    }
    if (STORE.currentScreen) renderScreenKeepingUi(STORE.currentScreen);
  } catch (e) {
    if (LIVE.sid !== sid) return;
    /* Render the server's own machine code and detail; a provider failure is technical, never a
       business verdict, and is never retold as one here. */
    const code = (e && e.code) ? String(e.code) : '';
    const msg = (e && e.detail && e.detail.message) ? String(e.detail.message)
      : ((e && e.message) ? e.message : 'Unknown error.');
    showToast((code ? 'Reassessment failed (' + code + '): ' : 'Reassessment failed: ') + msg, '', '', 'error');
  } finally {
    LIVE.reassessing = false;
    liveReassessButton(false);
  }
}
function cancelFinalize() { if (LIVE.finalizeAbort) LIVE.finalizeAbort.abort(); }
function resetDiagChatLive() {
  if (!window.confirm('Start the questions over? This begins a new map. Your current one stays in All maps.')) return;
  startNewMap();
}

/* Screen 01 (live): the goal text becomes the first message of a brand-new map. */
function liveIntakeSubmit(text) {
  if (!text) { const ta = document.getElementById('start-textarea'); if (ta) ta.focus(); return; }
  if (LIVE.sid || LIVE.artifact) liveForget();
  STORE.intakePrompt = '';
  STORE.chatEvidenceOpen = false;
  LIVE.err = ''; LIVE.msgs = [];
  liveSendMessage(text).then(() => renderChatLive());
  renderScreen('02');
  syncThinkingTimer();
}
