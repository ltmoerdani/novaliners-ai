// Laws of UX guard for the State destination (docs/09-design-research/07-30-laws-of-ux-jon-yablonski.md; prototype doc 02 §8).
// Runs in the page against whatever State screen is on screen, demo or live, and returns the violations (empty = clean) plus the
// numbers it measured, so a failure says which law broke and by how much. Shared by state-laws.spec.mjs and live.spec.mjs.
// Not every law can be measured in a browser; the ones that can are asserted here, the rest are judged in
// docs/07-design/diagnosis-screen-ux-laws-review.md (written for the v9 Diagnosis, the same laws now apply to State).
//
// State is the narrative first: the state told back in the person's own words, what holds the movement, then three numbered steps
// (1 next move and how you will know, 2 what not to do yet, 3 why), with a rail of numbers, paths and when to reassess. The prose
// is full width on purpose (owner decision 4 Oct 2026, doc 06 §9 note, doc 02 §8), so line length is not asserted.
//
// opts.plain: also check the words themselves (plain language). Off for artifacts that never got the plain-language rewrite, where
// the engine's own sentences are shown as they are.

export const HEADING = 'Where you are';
export const LIMITS = { proseWords: 520, actions: 6, sentence: 26, avgSentence: 20 };
// Words that mean nothing to an ordinary business owner (same idea as domains/revenue/guards/plain_language.py). "demand" is not here:
// the v11 State copy itself says "your skills and the demand are real" (prototype doc 02 §8).
export const JARGON = /\b(probe|funnel|icp|cac|ltv|kpi|roi|pipeline|feasibility|price[- ]?response|value[- ]framing|constraint|hipotesis|hypothesis|akuisisi|konversi|conversion|inquiry|eksperimen|intervensi|validasi|sampel|isolasi|baseline|benchmark|scaling|metrik|metric|traksi|traction|diagnostik|kontraindikasi)\b/i;
export const VERDICT_WORDS = /\b(gagal|salah|buruk|failed|failure|wrong|bad|incapable|kurang mampu)\b/i;

export async function checkStateLaws(page, opts = {}) {
  const plain = opts.plain !== false;
  return page.evaluate(([HEADING, LIMITS, JARGON_SRC, VERDICT_SRC, plain]) => {
    const out = []; const m = {};
    const root = document.getElementById('v11-main');
    if (!root || !root.querySelector('.dest-hero, .dest-focus')) return { violations: ['no State screen on screen'], metrics: m };
    const JARGON = new RegExp(JARGON_SRC, 'i'), VERDICT = new RegExp(VERDICT_SRC, 'i');
    const norm = t => t.replace(/\s+/g, ' ').trim();
    const rect = el => el.getBoundingClientRect();
    const sentencesOf = t => norm(t).split(/(?<=[.!?])\s+/).filter(Boolean);
    m.viewport = `${innerWidth}x${innerHeight}`;

    // Jakob, mental model: one h1, and the page opens with the state
    const h1s = root.querySelectorAll('h1');
    if (h1s.length !== 1) out.push(`Jakob: ${h1s.length} h1 on the page, expected 1`);
    else if (norm(h1s[0].textContent) !== HEADING) out.push(`Mental model: the page opens with "${norm(h1s[0].textContent)}", not "${HEADING}"`);

    // Serial position: the narrative, then what holds you, then the numbered steps in order
    const seq = [root.querySelector('.dest-hero'), root.querySelector('.dest-focus'), ...root.querySelectorAll('.dest-step')].filter(Boolean);
    for (let i = 1; i < seq.length; i++) if (rect(seq[i]).top <= rect(seq[i - 1]).top) out.push('Serial position: the blocks are not in reading order');
    const nums = [...root.querySelectorAll('.dest-step .dest-num')].map(n => norm(n.textContent));
    // a step with nothing to say is left out (no invented block), so the numbers run 1..n without a gap
    if (nums.length && JSON.stringify(nums) !== JSON.stringify(nums.map((_, i) => String(i + 1)))) out.push(`Serial position: steps are numbered [${nums.join(',')}], expected 1 to ${nums.length}`);

    // Cognitive load / Occam: the prose is short
    const prose = [...root.querySelectorAll('.dest-hero p, .dest-focus h2, .dest-step p, .dest-step h2, .dest-step li')].filter(e => !e.closest('details:not([open])'));
    m.proseWords = prose.reduce((n, e) => n + norm(e.innerText).split(' ').filter(Boolean).length, 0);
    if (m.proseWords > LIMITS.proseWords) out.push(`Cognitive load: the story shows ${m.proseWords} words (max ${LIMITS.proseWords})`);

    // Plain language (NN/g: short sentences, familiar words), personal and not a verdict. Visible text only.
    if (plain) {
      const all = [];
      for (const e of prose) {
        const t = norm(e.innerText); if (!t) continue;
        const j = JARGON.exec(t); if (j) out.push(`Plain language: technical word "${j[0]}" in "${t.slice(0, 50)}"`);
        if (/[→≠±—]|\(\d\)/.test(t) && !e.closest('button, a')) out.push(`Plain language: machine notation in "${t.slice(0, 50)}"`);
        if (VERDICT.test(t)) out.push(`Personal: judging word "${VERDICT.exec(t)[0]}" in "${t.slice(0, 50)}"`);
        for (const s of sentencesOf(t)) { const n = s.split(' ').length; all.push(n); if (n > LIMITS.sentence) out.push(`Plain language: a sentence of ${n} words (max ${LIMITS.sentence}): "${s.slice(0, 60)}"`); }
      }
      m.avgSentence = all.length ? Math.round(all.reduce((a, b) => a + b, 0) / all.length * 10) / 10 : 0;
      if (m.avgSentence > LIMITS.avgSentence) out.push(`Plain language: average sentence is ${m.avgSentence} words (max ${LIMITS.avgSentence})`);
      const hero = root.querySelector('.dest-hero');
      if (hero && !/\b(you|your)\b/i.test(norm(hero.innerText))) out.push('Personal: the opening never speaks to the reader');
    }

    // Hick, Von Restorff: one primary action at most, few choices on the page
    const isVis = e => rect(e).width > 0 && rect(e).height > 0;
    const actions = [...root.querySelectorAll('button, a[href], [onclick]')].filter(isVis);
    m.actions = actions.map(e => norm(e.innerText));
    if (actions.length > LIMITS.actions + 6) out.push(`Hick: ${actions.length} actions on the page: ${m.actions.join(' | ')}`);
    const primaries = root.querySelectorAll('.btn-primary');
    if (primaries.length > 1) out.push(`Hick / Von Restorff: ${primaries.length} primary buttons, expected at most 1`);

    // Tesler: nothing is cut with an ellipsis in the middle of a word, nothing sticks out sideways
    if (/(\S+\s)?\S*[a-z]…\S/.test(norm(root.innerText))) out.push('Tesler: an ellipsis sits inside a word');
    if (document.documentElement.scrollWidth > innerWidth + 1) out.push(`Layout: horizontal scroll (${document.documentElement.scrollWidth} > ${innerWidth})`);
    const clipped = [...root.querySelectorAll('*')].filter(e => { const r = rect(e); return r.width > 0 && r.right > innerWidth + 1.5 && !e.closest('svg'); });
    if (clipped.length) out.push(`Layout: ${clipped.length} element(s) stick out of the screen (${norm(clipped[0].innerText).slice(0, 30)})`);

    // Similarity: text that is not clickable is never underlined
    for (const e of root.querySelectorAll('p, h1, h2, b')) if (getComputedStyle(e).textDecorationLine.includes('underline') && !e.closest('button, a, summary')) out.push(`Similarity: "${norm(e.innerText).slice(0, 30)}" is underlined but not a control`);

    // Paradox of the active user: the reasoning is one click away
    if (!actions.some(e => /How we got here|Why we think so|Why/.test(e.innerText) || /openStateWhyDrawer/.test(e.getAttribute('onclick') || ''))) out.push('Paradox of the active user: the reasoning is not one click away');
    return { violations: out, metrics: m };
  }, [HEADING, LIMITS, JARGON.source, VERDICT_WORDS.source, plain]);
}

// Doherty Threshold: State renders, and the reasoning opens, well inside 400 ms
export async function measureResponse(page) {
  return page.evaluate(async () => {
    const t0 = performance.now(); goDestination('state'); const render = performance.now() - t0;
    const b = document.querySelector('[onclick*="openStateWhyDrawer"]');
    const t1 = performance.now(); b.click();
    const drawer = document.getElementById('why-drawer'); const opened = !!drawer && drawer.classList.contains('open'); const open = performance.now() - t1;
    if (typeof closeDrawer === 'function') closeDrawer();
    return { render, open, opened };
  });
}
