/* Readiness (screen 18): where each path stands, told in plain words with its evidence underneath.
   It is the second view of the Path map (header switch "Map | Readiness"): the map says WHERE you can go, this says
   WHAT each way stands on. internal-docs §3.
   Reading order per path: what the status means, what the path comes down to from where they are, then the evidence in
   three groups: What is already true · What is still missing · What we do not know yet. Counts confirm; they never
   read as progress toward 100% ("We can confirm 3 of the 6 conditions", no bar).
   v = { basics: [{ label, word, tone }], paths: [{ key, name, status, opening, supported, holding, unclear, basis,
   isActive, items: [item] }], sel }
   opening/supported/holding/unclear are the plain-language narrative (LLM rewrite with a deterministic fallback);
   empty means the section shows only its checklist items.
   item = { state: 'have' | 'need' | 'unknown', title, sub, soft, partial }   (title and sub are html-safe text) */
const RD_GROUPS = [
  { state: 'have', title: 'What is already true', empty: 'Nothing we can point to yet. That is normal early on.' },
  { state: 'need', title: 'What is still missing', empty: 'Nothing is missing that we know of.' },
  { state: 'unknown', title: 'What we do not know yet', empty: 'Everything has been checked.' }
];
const RD_MARK = { have: '✓', need: '', unknown: '?' };
const RD_STATUS_CLS = { OPEN: 'open', TEST_FIRST: 'test_first', NOT_YET: 'not_yet', STOP: 'stop' };
const RD_STATUS_WORD = { OPEN: 'OPEN', TEST_FIRST: 'TEST FIRST', NOT_YET: 'NOT YET', STOP: 'STOP' };
/* What the status pill means, said as an interpretation (never a verdict, never engine words).
 * OPEN (demo, pinned to the prototype) says the conditions are "in place"; live says what OPEN really means
 * (nothing seen blocks the path), because OPEN is not READY: the checklist below may still be mostly unchecked. */
const RD_STATUS_MEANING = {
  OPEN: 'The conditions this path needs are in place right now.',
  TEST_FIRST: 'This path may make sense, but an important assumption needs a real test first.',
  NOT_YET: 'There is a plausible path here, but something important is still missing.',
  STOP: 'What we have seen so far does not support spending effort here now.'
};

function rdCounts(p) {
  const n = s => p.items.filter(i => i.state === s).length;
  return { have: n('have'), need: n('need'), unknown: n('unknown'), total: p.items.length };
}
/* "We can confirm 3 of the 6 conditions so far." A confirmation, not progress toward a target. */
function rdCountLine(c) {
  return c.total ? `We can confirm ${c.have} of the ${c.total} conditions so far.`
    : 'We have not been able to check any condition for this path yet.';
}
/* Short form for compact spots: the path list, the map card, under a Diagnosis path. */
function rdInPlace(c) { return c.total ? `${c.have} of ${c.total} confirmed` : 'Nothing confirmed yet'; }

/* Short form for one path of a readiness model (the Diagnosis screen shows it under each path) */
function rdMetaOf(paths, key) { const p = paths.find(x => x.key === key); return p && p.items.length ? rdInPlace(rdCounts(p)) : ''; }

function rdItem(i) {
  return `
    <li class="rd-item ${i.state}">
      <span class="rd-mark" aria-hidden="true">${RD_MARK[i.state]}</span>
      <div>
        <div class="rd-item-title">${i.title}${i.partial ? '<span class="rd-tag">Partly there</span>' : ''}${i.soft ? '<span class="rd-tag">Helps</span>' : ''}</div>
        ${i.sub ? `<div class="rd-item-sub">${i.sub}</div>` : ''}
      </div>
    </li>`;
}

/* The path map's side card: what we can confirm here, and the first few things still open */
function renderMapNeed(p) {
  if (!p) return '';
  const c = rdCounts(p);
  const open = p.items.filter(i => i.state === 'need').concat(p.items.filter(i => i.state === 'unknown')).slice(0, 3);
  return `
        <div class="map-need">
          <div class="section-meta-label" style="margin-bottom:6px">What it needs</div>
          <div class="rd-count">${rdCountLine(c)}</div>
          ${open.length ? `<ul class="map-need-list">${open.map(i => `<li class="${i.state}"><span class="rd-mark" aria-hidden="true">${RD_MARK[i.state]}</span><span>${i.title}</span></li>`).join('')}</ul>` : ''}
        </div>`;
}

function renderReadinessLayout(v) {
  const p = v.paths.find(x => x.key === v.sel) || v.paths[0];
  const c = rdCounts(p);
  const group = g => {
    const items = p.items.filter(i => i.state === g.state);
    const note = g.state === 'have' ? p.supported : (g.state === 'need' ? p.holding : p.unclear);
    if (g.state === 'have' && !c.total) {   // nothing was checkable: the count line says it in full
      return `
      <section class="rd-group" aria-label="${g.title}">
        <h3 class="rd-group-head">${g.title}</h3>
        <div class="rd-empty">${rdCountLine(c)}</div>
      </section>`;
    }
    if (!items.length && g.state !== 'have') return '';   // an empty "missing" or "unknown" group says nothing: leave it out
    return `
      <section class="rd-group" aria-label="${g.title}">
        <h3 class="rd-group-head">${g.title}<span>${items.length}</span></h3>
        ${g.state === 'have' ? `<p class="rd-count">${rdCountLine(c)}</p>` : ''}
        ${note ? `<p class="rd-group-note">${note}</p>` : ''}
        ${items.length ? `<ul class="rd-list">${items.map(rdItem).join('')}</ul>`
          : (g.state === 'have' ? '' : `<div class="rd-empty">${g.empty}</div>`)}
      </section>`;
  };
  const unknownAsk = c.unknown ? `<button type="button" class="btn-secondary" onclick="openAsk('${esc(p.key)}')">Ask about what is not checked →</button>` : '';
  const go = p.isActive
    ? `<button type="button" class="btn-primary" onclick="renderScreen('04')">Go to Activity →</button>`
    : `<button type="button" class="btn-secondary" onclick="openPathOnMap('${esc(p.key)}')">See it on the path map →</button>`;
  return `
  <div class="diag-scroll"><div class="rd-layout">
    <header>
      <button type="button" class="btn-secondary" onclick="renderScreen('07')" style="margin-bottom:14px">← Back to path map</button>
      <h1 class="serif-heading" style="font-size:30px;margin:0">Where each path stands</h1>
      <p class="rd-sub">${v.shownLine ? 'These possibilities are' : (v.paths.length === 1 ? 'The path' : 'The same ' + countWord(v.paths.length).toLowerCase() + ' paths')} from your map, read from where you are: what is already true for each one, what is still missing, and what we do not know yet.${v.shownLine ? ' ' + v.shownLine + '.' : ''}</p>
    </header>

    <section class="card-clean rd-basics" aria-label="Your basics">
      <div class="section-meta-label" style="margin:0">Your basics</div>
      <div class="rd-basics-grid">${v.basics.map(b => `<div class="rd-basic"><span>${b.label}</span><span class="rd-word ${b.tone}">${b.word}</span></div>`).join('')}</div>
    </section>

    <div class="rd-body">
      <nav class="rd-paths" aria-label="Paths">${(v.shown || v.paths).map(x => {
        const k = rdCounts(x);
        return `
        <button type="button" class="rd-path" aria-pressed="${x.key === p.key}" onclick="selectReadinessPath('${esc(x.key)}')">
          <span class="rd-path-top"><span>${x.name}</span><span class="status-pill ${RD_STATUS_CLS[x.status]}">${RD_STATUS_WORD[x.status]}</span></span>
          <span class="rd-path-meta">${rdInPlace(k)}</span>
        </button>`;
      }).join('')}${v.overflow || ''}</nav>

      <section class="card-clean rd-detail" aria-label="${p.name}: where it stands">
        <div class="rd-detail-head">
          <div style="display:flex;align-items:baseline;flex-wrap:wrap"><h2>${p.name}</h2>${p.isActive ? '<span class="rd-current">● Your current path</span>' : ''}</div>
          <span class="status-pill ${RD_STATUS_CLS[p.status]}">${RD_STATUS_WORD[p.status]}</span>
        </div>
        <p class="rd-status-line">${(v.statusMeaning || RD_STATUS_MEANING)[p.status] || ''}</p>
        ${p.opening ? `<p class="rd-open">${p.opening}</p>` : (p.basis ? `<p class="rd-lead">${p.basis}</p>` : '')}
        ${v.whyHere || ''}
        ${RD_GROUPS.map(group).join('')}
        <div class="rd-actions">${go}${unknownAsk}</div>
      </section>
    </div>
    ${v.emerging || ''}
  </div></div>`;
}

/* Header switch shared by the two views of the Path map */
function renderMapSwitch(activeNav) {
  const onReadiness = activeNav === 'readiness';
  return `<div class="view-switch" role="group" aria-label="Path map views">
    <button type="button" aria-pressed="${!onReadiness}" onclick="renderScreen('07')">Map</button>
    <button type="button" aria-pressed="${onReadiness}" onclick="renderScreen('18')">Readiness</button>
  </div>`;
}

function selectReadinessPath(key) {
  STORE.readinessPath = key;
  renderScreen('18');
}
function openReadiness(key) {
  if (key) STORE.readinessPath = key;
  renderScreen('18');
}
function openPathOnMap(key) {
  STORE.selectedMapPath = key;
  renderScreen('07');
}

/* ── Demo (Dimas): the checklist follows the simulated 90 days ───────────────────────────────────── */
function demoReadiness() {
  const rs = useRoadmapStore.getState();
  const c = rs.currentCycle, done = rs.doneNums || [];
  const offer = c >= 2 || done.includes(1);
  const sent = c >= 2 || done.includes(2);
  const paid = rs.earned > 0;
  const auditOpen = rs.activePaths.includes('audit');
  const cmoOpen = rs.activePaths.includes('cmo');
  const tight = c >= 8;                       // Cycle 8: two paths open and only 6 free hours
  const saved = rs.moneySaved != null ? `Rp${rs.moneySaved}M saved` : 'Some savings set aside';
  const it = (state, title, sub, extra) => Object.assign({ state, title, sub: sub || '' }, extra || {});
  const active = toMapPath(rs.activePathId);
  const mk = (key, name, status, basis, items, nar) => Object.assign(
    { key, name, status, basis, items, isActive: active === key }, nar || {});
  const paths = [
    mk('warm', 'Advising people you know', 'OPEN', 'Win your first clients from the people who already know your work.', [
      it('have', 'People who know your work', 'You have 2 paid projects behind you.'),
      it('have', 'Two people waiting to hear from you', 'Both said "tell us when you start".'),
      offer ? it('have', 'A one-page offer', 'What you do, who it is for and the price, on one page.')
        : it('need', 'A one-page offer', 'Write what you do, who it is for and the price on one page.'),
      sent ? it('have', 'The offer in front of real people', 'It has been sent to the people who asked.')
        : it('need', 'The offer in front of real people', 'Send it to the 2 who asked to hear from you.'),
      paid ? it('have', 'A first paying client', 'Sari paid Rp15M for a brand audit.')
        : it('unknown', 'Someone willing to pay', 'We will know once someone replies with a price question or says yes.')
    ], {
      opening: 'You have done this work before for people who already knew you. What this path comes down to now is putting a price on it and letting the two who asked hear from you.',
      supported: 'Two people are waiting to hear from you, and 2 paid projects say your work lands. That is a real place to start from.',
      unclear: 'Whether one of them turns into a paying client, we do not know yet. It settles the moment someone answers your offer with a price question or a yes.'
    }),
    mk('agency', 'Freelancing for agencies', 'TEST_FIRST', 'Take overflow work from agencies while your own clients build up.', [
      it('have', 'Skills that agencies hire for', 'Brand strategy is what they outsource most.'),
      it('unknown', 'An agency that would hire you', 'Ask 3 agencies you know if they have overflow work.'),
      it('unknown', 'A day rate agencies accept', 'We cannot tell until an agency names a number.'),
      tight ? it('need', 'Free hours each week', 'Only 6 hours a week are free right now.') : it('have', 'Free hours each week', 'Your week has room for a few hours of extra work.')
    ], {
      opening: 'You would be doing the same brand strategy work, only with an agency as the client. For you this is a way to earn while your own client list is still short.',
      supported: 'The skills agencies hire for are the ones you already use every day.',
      unclear: 'Whether an agency would hire you, and at what day rate, is not known yet. Three conversations would settle both.'
    }),
    mk('audit', 'Fixed-price audit', auditOpen ? 'OPEN' : 'NOT_YET', 'Sell the same brand audit at one fixed price, again and again.', [
      paid ? it('have', 'One client who paid for an audit', 'Sari paid Rp15M for hers.')
        : it('need', 'One client who paid for an audit', 'A first paying client from the people you know opens this.'),
      auditOpen ? it('have', 'A second person asking for the same work', 'A second contact asked what an audit costs.')
        : it('need', 'A second person asking for the same work', 'Wait for, or ask for, a second request.'),
      auditOpen ? it('have', 'The audit written as a fixed package', 'Two weeks, one price, three parts.')
        : it('unknown', 'The audit written as a fixed package', 'We check this once the first audit is done.'),
      tight ? it('need', 'Hours free for audits', 'Audits take 4 hours a week and only 6 are free.') : it('have', 'Hours free for audits', 'An audit takes about 4 hours a week.')
    ], {
      opening: auditOpen
        ? 'One audit, one price, sold again and again. With the second request in, what this comes down to now is keeping the hours free to deliver it well.'
        : 'One audit, one price, sold again and again. From where you are, this comes down to one thing first: a second person asking for the same work.',
      supported: paid ? 'Sari paid Rp15M for an audit, so the work itself is proven with a real client.' : '',
      holding: paid ? '' : 'It waits on a first client paying for an audit. The people you already know can open that door.',
      unclear: auditOpen ? '' : 'Whether the audit works as a fixed package is something we can only check after the first one is done.'
    }),
    mk('cmo', 'Part-time marketing lead', cmoOpen ? 'OPEN' : 'NOT_YET', 'Become the monthly marketing lead for a brand that trusts you.', [
      cmoOpen ? it('have', 'Two audits sold at full price', 'Both were paid at Rp15M.') : it('need', 'Two audits sold at full price', 'Two clients paying the full audit price opens this.'),
      cmoOpen ? it('have', 'A brand that asked for ongoing help', 'A former audit client asked you to keep helping.') : it('unknown', 'A brand that asked for ongoing help', 'Ask your audit clients if they want monthly help.'),
      tight ? it('need', 'Hours for a monthly role', 'The role needs 5 hours a week and only 6 are free.') : it('unknown', 'Hours for a monthly role', 'We cannot check until you know how many days a month it takes.')
    ], {
      opening: 'One brand trusting you with its marketing every month. From where you stand, this grows out of the audit work rather than starting something new.',
      supported: cmoOpen ? 'Two audits sold at full price, and a client who asked you to stay on. The door into this path is already open.' : '',
      holding: cmoOpen ? (tight ? 'Hours are what presses on this path: the role needs 5 a week and only 6 are free.' : '') : 'It waits on the audits selling first.',
      unclear: cmoOpen ? '' : 'Whether an audit client wants monthly help is not known until you ask.'
    }),
    mk('ads', 'Paid LinkedIn ads', 'STOP', 'Pay for attention once an offer already sells without you.', [
      it('need', 'An offer that sells without you', 'Sell it at full price at least twice first.'),
      it('need', 'Proof that this audience buys', 'Ads only make sense after a few people from LinkedIn have said yes.'),
      it('unknown', 'What a client costs you to win', 'A capped Rp2M test would tell you.'),
      it('have', 'Money you can afford to test with', saved + '.')
    ], {
      opening: 'This means paying LinkedIn to put your offer in front of more people. What we have seen so far says the offer is not ready to carry that.',
      supported: 'The test budget is set aside, so money will not be what stops you.',
      holding: 'Two things come first: an offer that sells without you, and proof that this audience buys at all.',
      unclear: 'What a client costs you to win there, we cannot say yet. A small capped test would answer it, later.'
    })
  ];
  const basics = [
    { label: 'Getting clients', word: 'Partly ready', tone: 'warn' },
    { label: 'Turning talks into deals', word: paid ? 'Partly ready' : 'Not measured', tone: paid ? 'warn' : 'muted' },
    { label: 'Delivering the work', word: tight ? 'Held back' : 'Ready', tone: tight ? 'warn' : 'ok' },
    { label: 'Scaling up', word: 'Not ready', tone: 'stop' }
  ];
  const sel = paths.find(p => p.key === STORE.readinessPath) ? STORE.readinessPath : active;
  return { basics, paths, sel };
}
