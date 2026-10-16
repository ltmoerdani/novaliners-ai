/* Overlays + dispatcher */
/* ── Screen 09 Drawer (Full Reasoning Trace) ───────────────────────────── */
function openDrawerDemo() {
  document.getElementById('drawer-content').innerHTML = `
    <div style="padding:28px 32px 64px;display:flex;flex-direction:column;gap:24px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div class="section-meta-label">Why this diagnosis?</div>
          <h2 class="serif-heading" style="font-size:28px;margin-top:2px">How we reached this diagnosis</h2>
          <p style="font-size:13px;color:var(--ink-2);margin-top:4px">
            AI reads your answers. Fixed rules do the scoring, so the same answers always give the same result.
          </p>
        </div>
        <button onclick="closeDrawer()" style="font-size:22px;color:var(--ink-3);background:none;border:none;cursor:pointer">✕</button>
      </div>

      <!-- 1. What You Told Us -->
      <div class="card-clean" style="padding:18px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <span class="section-meta-label">1. What you told us</span>
          <span style="font-family:var(--font-ui);font-size:10.5px;font-weight:700;color:var(--ink-2);background:var(--surface-tint);border:1px solid var(--border);padding:2px 8px;border-radius:4px">Read by AI</span>
        </div>
        
        <div style="border:1.5px solid var(--ink);border-radius:8px;padding:12px;background:var(--surface);margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;align-items:center;font-size:12.5px;font-weight:700">
            <span>2 contacts asked to hear from you</span>
            <span style="color:var(--open-fg)">+2.0 pts</span>
          </div>
          <blockquote style="font-style:italic;font-size:13px;color:var(--ink-2);margin:6px 0">
            “Two people told me to let them know if I ever started my own business.”
          </blockquote>
          <div style="font-size:11px;color:var(--ink-3)">Your words · question 4 · Something people did · Strong · Supports reason 1</div>
        </div>

        <div style="display:flex;flex-direction:column;gap:8px;font-size:12.5px">
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
            <span>2 paid projects outside your salary</span>
            <span style="font-weight:700;color:var(--open-fg)">+3.0 pts</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
            <span>No one contacted directly in 30 days</span>
            <span style="font-weight:700;color:var(--open-fg)">+2.0 pts</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">
            <span>No written offer or price list</span>
            <span style="font-weight:700;color:var(--open-fg)">+2.0 pts</span>
          </div>
          <div style="display:flex;justify-content:space-between;padding:6px 0;color:var(--ink-muted)">
            <span>“I need an office first”</span>
            <span>A guess, so not scored</span>
          </div>
        </div>
      </div>

      <!-- 2. What Could Explain It -->
      <div class="card-clean" style="padding:18px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <span class="section-meta-label">2. What could explain it</span>
          <span style="font-family:var(--font-ui);font-size:10.5px;font-weight:700;color:var(--ink-2);background:var(--surface-2);padding:2px 8px;border-radius:4px">Scored by rules</span>
        </div>

        <div style="display:flex;flex-direction:column;gap:10px;margin-top:6px">
          <div>
            <div style="display:flex;justify-content:space-between;font-size:12.5px;font-weight:700;margin-bottom:4px">
              <span>Reason 1: No written offer or clear service</span>
              <span>9.0 pts · 88%</span>
            </div>
            <div style="height:8px;background:var(--surface-2);border-radius:999px;overflow:hidden">
              <div style="width:88%;height:100%;background:var(--ink);border-radius:999px"></div>
            </div>
          </div>
          <div>
            <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--ink-3);margin-bottom:4px">
              <span>Reason 2: Aiming at the wrong buyers</span>
              <span>0.6 pts · 6%</span>
            </div>
            <div style="height:6px;background:var(--surface-2);border-radius:999px;overflow:hidden">
              <div style="width:6%;height:100%;background:var(--ink-muted);border-radius:999px"></div>
            </div>
          </div>
          <div>
            <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--ink-3);margin-bottom:4px">
              <span>Reason 3: Price seems too high</span>
              <span>0.6 pts · 6%</span>
            </div>
            <div style="height:6px;background:var(--surface-2);border-radius:999px;overflow:hidden">
              <div style="width:6%;height:100%;background:var(--ink-muted);border-radius:999px"></div>
            </div>
          </div>
        </div>

        <div style="font-size:11.5px;color:var(--ink-3);line-height:1.45;margin-top:12px;border-top:1px solid var(--border);padding-top:8px">
          How points work: a payment counts 3, something someone did counts 2, something someone said counts 1, then adjusted for how strong it is. Guesses never count. Confidence is each reason's share of all points.
        </div>
      </div>

      <!-- 3. Readiness Check -->
      <div class="card-clean" style="padding:18px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <span class="section-meta-label">3. Are you ready to act?</span>
          <span style="font-family:var(--font-ui);font-size:10.5px;font-weight:700;color:var(--ink-2);background:var(--surface-2);padding:2px 8px;border-radius:4px">Checked by rules</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">
          <div style="padding:6px 10px;background:var(--open-soft);border-radius:6px;color:var(--open-fg);font-weight:600">✓ People have paid you before</div>
          <div style="padding:6px 10px;background:var(--open-soft);border-radius:6px;color:var(--open-fg);font-weight:600">✓ 2 people asked about your work</div>
          <div style="padding:6px 10px;background:var(--open-soft);border-radius:6px;color:var(--open-fg);font-weight:600">✓ 5+ months of savings</div>
          <div style="padding:6px 10px;background:var(--ink);color:var(--on-ink);border-radius:6px;font-weight:700;text-align:center">Verdict: GO SMALL</div>
        </div>
      </div>

      <!-- 4. What We Blocked & Why -->
      <div class="card-clean" style="padding:18px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
          <span class="section-meta-label">4. What we blocked, and why</span>
          <span style="font-family:var(--font-ui);font-size:10.5px;font-weight:700;color:var(--ink-2);background:var(--surface-2);padding:2px 8px;border-radius:4px">Based on fixed rules</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px;font-size:12.5px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span>Paid ads: no proven offer yet, so nothing to advertise</span>
            <span class="status-pill stop">STOP</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span>Renting an office: no client has asked for it</span>
            <span class="status-pill not_yet">NOT YET</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span>Registering a company: fewer than 3 paying clients so far</span>
            <span class="status-pill not_yet">NOT YET</span>
          </div>
        </div>
      </div>

      <div style="display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--border);padding-top:16px">
        <span style="font-size:12px;color:var(--ink-3)">Something wrong here? Fix it and we'll score it again.</span>
        <button class="btn-secondary btn-sm" onclick="closeDrawer();renderScreen('02')">Correct an answer</button>
      </div>
    </div>
  `;
  document.getElementById('why-drawer').classList.add('open');
  overlayOpened('why-drawer');
}
function closeDrawer() { const el = document.getElementById('why-drawer'); if (el.classList.contains('open')) { el.classList.remove('open'); overlayClosed(); } }

/* ── Screen 11 Modal (Doing Stopped Path Anyway) ────────────────────────── */
function openModalDemo() {
  const reason = STORE.adsAppealReason || 'network';
  const choice = STORE.adsActionChoice || 'capped';

  let reasonNote = "";
  if (reason === 'network') {
    reasonNote = "<strong style='color:var(--open-fg)'>We'll work around this:</strong> We'll reorder your paths toward ones that don't depend on messaging people you know. Freelancing for agencies moves up as your next test.";
  } else if (reason === 'reach') {
    reasonNote = "<strong style='color:var(--ink)'>Why reaching more people can wait:</strong> Reaching more people pays off once people say yes to your offer. Right now there's no written offer to show them. Writing it makes everything after it work better.";
  } else if (reason === 'someone') {
    reasonNote = "<strong style='color:var(--ink)'>Often true, but later:</strong> Ads tend to work for offers that already sell. We'll bring this path back up once your audit offer has paying clients.";
  } else {
    reasonNote = "<strong style='color:var(--ink)'>Tell us in your own words:</strong> Explain it in the chat, in any language. Your reason becomes evidence, and we'll re-check the map with it.";
  }

  document.getElementById('modal-content').innerHTML = `
    <div style="display:flex;flex-direction:column;gap:20px;max-height:85vh;overflow-y:auto;padding-right:4px">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
            <span class="section-meta-label">Paid LinkedIn ads</span>
            <span class="status-pill stop">STOP</span>
          </div>
          <h2 class="serif-heading" style="font-size:28px">You'd like to run ads anyway. It's your call.</h2>
          <p style="font-size:13.5px;color:var(--ink-2);margin-top:4px">Here's what the evidence says, what it could cost, and a safer way to try it.</p>
        </div>
        <button onclick="closeModal()" style="font-size:22px;color:var(--ink-3);background:none;border:none;cursor:pointer">✕</button>
      </div>

      <!-- Two Info Boxes -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px">
        <div style="background:var(--surface-2);border-radius:10px;padding:14px">
          <div class="section-meta-label">What we see</div>
          <div style="font-size:13px;color:var(--ink);line-height:1.5;margin-top:4px">
            No written offer yet, 0 buyers contacted, and both past clients came through people who knew you.
          </div>
        </div>
        <div style="background:var(--stop-soft);border:1px solid var(--stop-border);border-radius:10px;padding:14px">
          <div class="section-meta-label" style="color:var(--stop-fg)">What it could cost</div>
          <div style="font-size:13px;color:var(--ink);line-height:1.5;margin-top:4px">
            Rp10M is 20% of your savings, about 1.2 months of living costs.
          </div>
        </div>
      </div>

      <!-- What's making ads appealing? -->
      <div>
        <div class="section-meta-label mb-8">What's making ads appealing right now?</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          <button class="example-chip-box ${reason === 'network' ? 'selected' : ''}" style="${reason === 'network' ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="setAdsAppealReason('network')">I'd rather not message people I know</button>
          <button class="example-chip-box ${reason === 'reach' ? 'selected' : ''}" style="${reason === 'reach' ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="setAdsAppealReason('reach')">I want to reach more people, faster</button>
          <button class="example-chip-box ${reason === 'someone' ? 'selected' : ''}" style="${reason === 'someone' ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="setAdsAppealReason('someone')">Someone told me ads work</button>
          <button class="example-chip-box ${reason === 'other' ? 'selected' : ''}" style="${reason === 'other' ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="setAdsAppealReason('other')">Something else</button>
        </div>
        <div style="background:var(--surface-2);border-radius:8px;padding:10px 12px;font-size:12.5px;color:var(--ink);line-height:1.5;margin-top:10px">
          ${reasonNote}
        </div>
      </div>

      <!-- Action Choice RadioCards -->
      <div>
        <div class="section-meta-label mb-8">What would you like to do?</div>
        <div style="display:flex;flex-direction:column;gap:10px">
          <div class="radio-card ${choice === 'capped' ? 'selected' : ''}" onclick="setAdsActionChoice('capped')">
            <div class="radio-dot"></div>
            <div>
              <div style="display:flex;align-items:center;gap:8px">
                <span style="font-family:var(--font-ui);font-weight:700;font-size:14px">Run a small test instead</span>
                <span class="status-pill open" style="padding:1px 6px;font-size:10px">RECOMMENDED</span>
              </div>
              <div style="font-size:12.5px;color:var(--ink-2);margin-top:2px">
                Rp2M, not Rp10M, starting once your one-page offer is written. It stops by itself on Day 14 if no serious buyer books a call.
              </div>
            </div>
          </div>

          <div class="radio-card ${choice === 'full' ? 'selected' : ''}" onclick="setAdsActionChoice('full')">
            <div class="radio-dot"></div>
            <div>
              <div style="font-family:var(--font-ui);font-weight:700;font-size:14px">Go ahead with the full Rp10M plan</div>
              <div style="font-size:12.5px;color:var(--ink-2);margin-top:2px">
                We'll log it as your decision, track the result honestly, and your map will learn from it either way.
              </div>
            </div>
          </div>

          <div class="radio-card ${choice === 'stop' ? 'selected' : ''}" onclick="setAdsActionChoice('stop')">
            <div class="radio-dot"></div>
            <div>
              <div style="font-family:var(--font-ui);font-weight:700;font-size:14px">Keep it stopped for now</div>
              <div style="font-size:12.5px;color:var(--ink-2);margin-top:2px">
                Nothing changes. You can come back to this any time.
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer Buttons -->
      <div style="display:flex;justify-content:flex-end;gap:10px;border-top:1px solid var(--border);padding-top:14px">
        <button class="btn-secondary btn-sm" onclick="closeModal()">Cancel</button>
        <button class="btn-primary btn-sm" onclick="confirmAdsModalChoice()">Confirm choice →</button>
      </div>
    </div>
  `;
  document.getElementById('stop-modal').classList.add('open');
  overlayOpened('stop-modal');
}
function closeModal() { const el = document.getElementById('stop-modal'); if (el.classList.contains('open')) { el.classList.remove('open'); overlayClosed(); } }
function setAdsAppealReason(val) {
  STORE.adsAppealReason = val;
  openModal();
}

function setAdsActionChoice(val) {
  STORE.adsActionChoice = val;
  openModal();
}


/* Dialog behaviour (spec §7): focus moves in, Tab stays inside, Esc closes, focus returns on close. */
let overlayReturnFocus = null, overlayReturnKey = null;
function overlayOpened(id) {
  if (IS_DEMO) return;                          // design review keeps the prototype's exact pixels (no focus ring)
  if (overlayReturnFocus) return;               // re-render of an open dialog (e.g. picking a chip): keep focus where it is
  overlayReturnFocus = document.activeElement || document.body;
  overlayReturnKey = typeof uiKeyOf === 'function' ? uiKeyOf(overlayReturnFocus) : null;   // to find the opener again if the page re-rendered under the dialog
  document.getElementById('app-root').inert = true;      // the page behind a dialog is neither focusable nor read out
  const root = document.getElementById(id);
  setTimeout(() => {
    if (!root.classList.contains('open')) return;   // closed again before the timer fired (a fast Escape): never pull focus back into a closed dialog
    const f = root.querySelector('button, [href], input, [tabindex]:not([tabindex="-1"])');
    if (f) f.focus();
  }, 60);
}
function overlayClosed() {
  const app = document.getElementById('app-root'); if (app) app.inert = false;
  let back = overlayReturnFocus;
  if ((!back || !document.body.contains(back)) && overlayReturnKey) { try { back = document.querySelector('#app-root ' + overlayReturnKey); } catch (e) { back = null; } }
  if (back && document.body.contains(back)) { try { back.focus(); } catch (e) { /* ignore */ } }
  overlayReturnFocus = null; overlayReturnKey = null;
}
document.addEventListener('keydown', e => {
  const open = document.querySelector('.drawer-backdrop.open, .modal-backdrop.open');
  if (!open) return;
  if (e.key === 'Escape') { e.preventDefault(); closeDrawer(); closeModal(); return; }
  if (e.key !== 'Tab') return;
  const f = [...open.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter(x => !x.disabled && x.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  else if (!open.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
});
