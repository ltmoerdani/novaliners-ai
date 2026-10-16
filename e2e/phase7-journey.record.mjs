// Phase 7 end-to-end recorder (paced for human review: ~2 minutes).
// Create Map -> interview Q&A -> diagnosis -> Maps -> the canonical Move's actions ticked in
// Moves -> the SAME move changes on Maps -> the result is reported on the move.
// Requires a MOCK-provider server. Recording only: no assertions block the video.
//   cd mvp/e2e && P7_BASE=http://127.0.0.1:8791 node phase7-journey.record.mjs
import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const BASE = process.env.P7_BASE || 'http://127.0.0.1:8791';
const OUT = process.env.P7_OUT || path.resolve('__video__');
fs.mkdirSync(OUT, { recursive: true });

const report = { base: BASE, startedAt: new Date().toISOString(), steps: [], verdict: 'UNKNOWN' };
const step = (name, ok, detail) => {
  report.steps.push({ name, ok: !!ok, detail: detail === undefined ? '' : String(detail) });
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? ' :: ' + detail : ''));
};

const browser = await chromium.launch();
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 }, locale: 'en-GB', timezoneId: 'Asia/Jakarta',
  reducedMotion: 'reduce', recordVideo: { dir: OUT, size: { width: 1440, height: 900 } }
});
const page = await context.newPage();
page.on('dialog', d => d.accept());
const hold = ms => page.waitForTimeout(ms);
const shot = async n => { await page.screenshot({ path: path.join(OUT, n + '.png') }); };
const moveState = () => page.evaluate(() => {
  const rows = (typeof liveMoveRows === 'function') ? liveMoveRows() : [];
  return rows.map(m => ({ move_id: m.move_id, lifecycle: m.lifecycle, path: m.linked_path_id,
    actions: (m.actions || []).map(a => ({ id: a.action_id, title: a.title, status: a.status, required: a.required !== false })) }));
});
const nav = name => page.locator('.v11-topnav-item', { hasText: new RegExp('^' + name + '$') });

try {
  await page.addInitScript(() => { try { localStorage.setItem('novaliners-v9', JSON.stringify({ userId: 'u_p7v' + Math.random().toString(16).slice(2, 8), chain: [], checkins: [], overrides: [], tips: {} })); } catch (e) {} });
  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.waitForSelector('#start-textarea', { timeout: 30000 });
  await hold(2500);
  await shot('01-start');
  step('start screen', true);

  const story = 'I left my job as a marketing manager. I want Rp20 million a month from consulting within 90 days. '
    + 'Right now I make Rp8 million a month from two retainer clients. Two past clients asked me to let them know '
    + 'when I have room for a short project, and last year one paid Rp5 million for a two-week audit. '
    + 'I have about 10 hours a week and no ads budget.';
  await page.locator('#start-textarea').pressSequentially(story, { delay: 12 });
  await hold(1200);
  await page.getByRole('button', { name: /Start my diagnosis/ }).click();
  await page.waitForURL(/diagnosis/, { timeout: 60000 });
  await page.waitForSelector('#diag-chat-input:not([disabled])', { timeout: 120000 });
  await hold(3000);
  await shot('02-interview-first-question');
  step('interview opens', true, await page.evaluate(() => (document.querySelector('#nav-focus') || {}).innerText || ''));

  const answers = [
    'My income now is Rp8 million a month from 2 clients and it is steady.',
    'Two past clients asked me to let them know when I have room, and one paid Rp5 million last year.',
    'I charge Rp4 million for a two-week audit and I can take one more project without hiring anyone.'
  ];
  for (let i = 0; i < answers.length; i++) {
    await hold(2200);
    await page.locator('#diag-chat-input').pressSequentially(answers[i], { delay: 10 });
    await hold(900);
    await page.keyboard.press('Enter');
    await page.waitForSelector('#diag-chat-input:not([disabled])', { timeout: 120000 });
    await hold(2600);
    step('interview turn ' + (i + 1), true);
  }
  await shot('03-interview-answered');
  await hold(1500);
  await page.getByText('Enough answers? Build my diagnosis now').click();
  await page.waitForSelector('.v11-topnav-item', { timeout: 180000 });
  await hold(4000);
  await shot('04-diagnosis');
  step('diagnosis built', true, page.url());

  await nav('Maps').click();
  await page.waitForSelector('#v12-map svg', { timeout: 90000 });
  await hold(4500);
  const paths = await page.evaluate(() => (V11_ENGINE.snapshot().paths || []).length);
  await shot('05-maps-before');
  step('maps shows the paths', paths > 0, 'paths=' + paths);

  await nav('Moves').click();
  await page.waitForURL(/moves/, { timeout: 30000 });
  await hold(3500);
  await shot('06-moves-before');
  let moves = await moveState();
  if (!moves.some(m => m.lifecycle === 'PLANNED' || m.lifecycle === 'STARTED')) {
    const ask = page.getByRole('button', { name: /Ask the engine for the next move/ });
    if (await ask.count()) {
      await hold(2000);
      await ask.first().click();
      await hold(4000);
      moves = await moveState();
      step('asked the engine for the next move', true, JSON.stringify(moves));
      await shot('06b-after-ask');
    }
  }
  if (!moves.some(m => m.lifecycle === 'PLANNED' || m.lifecycle === 'STARTED')) {
    /* RECORDING SEED: the engine answered with a question, so no canonical Move exists to tick.
       This creates one through the SAME create_move the engine uses (dev route, env-gated, not
       committed). Everything after this point goes through the normal endpoints. */
    const seeded = await page.evaluate(async () => {
      const snap = V11_ENGINE.snapshot();
      const pid = (snap.paths && snap.paths[0] && snap.paths[0].id) || '';
      const design = {
        objective: 'Check interest from past clients',
        actions: [
          { title: 'Select two relevant past clients', instruction: 'Pick the two who asked you to let them know.' },
          { title: 'Prepare and send a short message', instruction: 'Say what you offer and what it costs.' },
          { title: 'Follow up about their interest', instruction: 'Only if they have not replied in three days.', depends_on: [1, 2] }
        ],
        expected_evidence: ['Two replies from past clients'],
        measurement_method: 'Count the replies within seven days',
        observation_window_days: 7,
        completion_criteria: ['Two clients contacted', 'Every reply recorded'],
        linked_path_id: pid
      };
      const r = await fetch('/admin/seed_move', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: LIVE.sid, design: design, text: 'Ask two past clients.', event_id: 'ce-seed-phase7' }) });
      const j = await r.json().catch(() => ({}));
      if (j && j.ok) { await liveRefreshAfterMutation(); }
      return j;
    });
    await hold(3500);
    moves = await moveState();
    step('recording seed created a canonical move', !!(seeded && seeded.ok), JSON.stringify(seeded).slice(0, 160));
    await shot('06c-move-created');
  }
  const target = moves.find(m => m.lifecycle === 'PLANNED' || m.lifecycle === 'STARTED') || moves[moves.length - 1] || null;
  step('a canonical move exists with an action list', !!(target && target.actions.length), JSON.stringify(target));
  report.move_id = target ? target.move_id : null;

  if (target && target.actions.length) {
    const requiredIds = target.actions.filter(a => a.required).map(a => a.id);
    for (const id of requiredIds) {
      const row = page.locator('.mv-action[data-action-id="' + id + '"]');
      await row.scrollIntoViewIfNeeded();
      await hold(2200);
      const btn = row.getByRole('button', { name: 'Record as done' });
      if (!(await btn.count())) { step('tick action ' + id, false, 'no Record-as-done control'); continue; }
      await btn.first().click();
      await hold(3000);
      const after = await moveState();
      const m2 = after.find(m => m.move_id === target.move_id) || {};
      const doneN = (m2.actions || []).filter(a => a.status === 'DONE').length;
      step('tick action ' + id, true, 'lifecycle=' + m2.lifecycle + ' done=' + doneN + '/' + (m2.actions || []).length);
    }
    await hold(3000);
    await shot('07-moves-after-ticks');
    const final = (await moveState()).find(m => m.move_id === target.move_id) || {};
    step('the SAME move advanced to EXECUTED', final.lifecycle === 'EXECUTED', 'lifecycle=' + final.lifecycle);
    report.lifecycle_after_ticks = final.lifecycle;

    /* The completion prompt opens BY ITSELF after the last required action; open it only when it did not. */
    let modalOpen = await page.locator('#stop-modal.open').count();
    if (!modalOpen) {
      const reportBtn = page.getByRole('button', { name: /Report outcome/ });
      if (await reportBtn.count()) { await reportBtn.first().click(); await hold(2500); modalOpen = await page.locator('#stop-modal.open').count(); }
    }
    if (modalOpen) {
      await hold(2000);
      await shot('08-outcome-dialog');
      const choice = page.getByText('Something moved', { exact: true });
      if (await choice.count()) { await choice.first().click(); await hold(1200); }
      const save = page.locator('#mr-submit');
      if (await save.count()) { await save.first().click(); await hold(4000); }
      await shot('09-after-outcome');
      const afterOutcome = (await moveState()).find(m => m.move_id === target.move_id) || {};
      step('result recorded on the move', afterOutcome.lifecycle === 'OBSERVED', 'lifecycle=' + afterOutcome.lifecycle);
    } else {
      step('result prompt offered', false, 'no outcome dialog');
    }

    /* ── THE NEXT MOVE ───────────────────────────────────────────────────────────────────────
       Ask the engine for the next work. If it authorizes an ACTION the Move comes from the
       reasoner; if the route frontier authorizes an EXECUTE the server materialises it from that
       node (deterministic). If neither is authorized yet, the recording seeds the next Move through
       the SAME create_move (dev route, env-gated) so the NEXT node can be seen with its real name. */
    await hold(1500);
    await nav('Moves').click();
    await page.waitForURL(/moves/, { timeout: 30000 });
    await hold(2500);
    const ask2 = page.getByRole('button', { name: /Ask the engine for the next move/ });
    if (await ask2.count()) { await ask2.first().click(); await hold(4500); }
    let all2 = await moveState();
    let second = all2.find(m => (m.lifecycle === 'PLANNED' || m.lifecycle === 'STARTED') && m.move_id !== target.move_id) || null;
    if (!second && process.env.P7_ALLOW_SEED === '1') {
      const seeded2 = await page.evaluate(async (firstId) => {
        const rows = liveMoveRows();
        const first = rows.find(m => m.move_id === firstId) || rows[0];
        const design = {
          objective: 'Create the proposal for the two past clients',
          actions: [
            { title: 'Write the one-page proposal', instruction: 'Scope, price and start date, on one page.' },
            { title: 'Send it to both past clients', instruction: 'The same message, adapted per client.', depends_on: [1] }
          ],
          expected_evidence: ['Both clients received the proposal'],
          measurement_method: 'Note who replied and what they asked',
          observation_window_days: 7,
          completion_criteria: ['The proposal is written', 'It was sent to both clients'],
          linked_path_id: (first && first.linked_path_id) || ((V11_ENGINE.snapshot().paths[0] || {}).id || '')
        };
        const r = await fetch('/admin/seed_move', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: LIVE.sid, design: design, text: 'Create the proposal.', event_id: 'ce-seed-phase7-b' }) });
        const j = await r.json().catch(() => ({}));
        if (j && j.ok) { await liveRefreshAfterMutation(); }
        return j;
      }, target.move_id);
      await hold(3500);
      all2 = await moveState();
      second = all2.find(m => m.move_id !== target.move_id && (m.lifecycle === 'PLANNED' || m.lifecycle === 'STARTED')) ||
        all2.find(m => m.move_id !== target.move_id) || null;
      step('recording seed created the NEXT move', !!(seeded2 && seeded2.ok), (second && second.move_id) || '');
    } else if (second) {
      step('the engine authorized the next move by itself', true, second.move_id);
    } else {
      /* No next Move yet: record the HONEST state the engine returned instead of fabricating work. */
      await shot('10-frontier-honest');
      step('no next move authorized yet - frontier recorded', true,
        JSON.stringify(await page.evaluate(() => (LIVE.moves && LIVE.moves.frontier) || null)));
    }
    await hold(2500);
    await shot('10-moves-next');
    if (second) {
      report.next_move_id = second.move_id;
      const req2 = (second.actions || []).filter(a => a.required).map(a => a.id);
      for (const id of req2) {
        const row = page.locator('.mv-action[data-action-id="' + id + '"]');
        await row.scrollIntoViewIfNeeded();
        await hold(2000);
        const btn = row.getByRole('button', { name: 'Record as done' });
        if (await btn.count()) { await btn.first().click(); await hold(3000); }
      }
      const after2 = (await moveState()).find(m => m.move_id === second.move_id) || {};
      step('the NEXT move advanced on its own id', after2.lifecycle === 'EXECUTED', 'lifecycle=' + after2.lifecycle);
      await shot('11-moves-next-done');
      /* finishing a move's required actions opens the result prompt by itself: close it before the
         map is opened, otherwise the dialog correctly blocks the navigation. */
      await hold(1500);
      if (await page.locator('#stop-modal.open').count()) {
        await page.evaluate(() => { try { closeModal(); } catch (e) {} });
        await hold(1500);
      }
    }

    await hold(1500);
    await nav('Maps').click();
    await page.waitForSelector('#v12-map svg', { timeout: 60000 });
    await hold(4500);
    const station = page.locator('[data-v12-move="' + target.move_id + '"]');
    const n = await station.count();
    if (n) {
      /* Move the real pointer over the station so the recording shows WHICH node it is; a synthetic
         hover on the <g> is swallowed by the map's own pointer handling. */
      const box = await station.first().boundingBox();
      if (box) { await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2); await hold(2200); }
    }
    const title = n ? (await station.first().evaluate(el => { const t = el.querySelector('title'); return t ? t.textContent : el.getAttribute('aria-label') || ''; })) : '';
    const seqNow = await page.evaluate(() => { const s = V11_ENGINE.snapshot(); const p = (s.paths || []).find(x => (x.canonical_moves || []).length) || {}; return (p.canonical_moves || []).map(m => m.title + ' · ' + m.lifecycle); });
    await shot('12-maps-two-moves');
    step('maps renders the SAME move_id', n > 0, 'stations=' + n + ' | ' + title);
    step('maps shows the NEW move as its own node', (report.next_move_id ? (await page.locator('[data-v12-move="' + report.next_move_id + '"]').count()) > 0 : false), JSON.stringify(seqNow));
    report.maps_station_title = title;
    report.maps_stations = n;
    report.maps_sequence = seqNow;
    await hold(4000);
    await nav('Journey').click();
    await hold(4000);
    await shot('11-journey');
    step('journey reached', true, page.url());
    await hold(2000);
  }
  report.verdict = report.steps.every(s => s.ok) ? 'PASS' : 'PARTIAL';
} catch (e) {
  report.verdict = 'ERROR';
  report.error = String(e && e.message || e);
  step('run aborted', false, report.error);
  try { await shot('99-failure'); } catch (x) {}
} finally {
  report.finishedAt = new Date().toISOString();
  await hold(1500);
  await context.close();
  const v = page.video();
  if (v) { try { report.video = await v.path(); } catch (e) { report.video = null; } }
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 2));
  console.log('VIDEO ' + (report.video || 'none'));
  console.log('VERDICT ' + report.verdict);
  await browser.close();
}
