/* Update screens 06a 06b 12 + persona screens */
/* ── Screen 06a · Map updated (AppShell + Sidebar 256px) ─────────────────── */
function screen06a() {
  const content = `
  <div style="padding:40px 56px;display:flex;flex-direction:column;gap:28px">
    <div style="display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:16px">
      <div>
        <div class="section-meta-label" style="color:var(--open-fg)">Map updated from your Day 7 check-in</div>
        <h1 class="serif-heading" style="font-size:36px">A new path just opened.</h1>
        <p style="font-size:14.5px;color:var(--ink-2);margin-top:6px">Your goal stays the same: Rp30M a month. You just have better options now.</p>
      </div>
      <div style="text-align:right">
        <div style="display:flex;align-items:center;gap:10px;justify-content:flex-end">
          <span style="font-family:var(--font-ui);font-size:13px;font-weight:700">Rp15M of Rp30M</span>
          <div style="width:120px;height:8px;background:var(--border);border-radius:999px;overflow:hidden">
            <div style="width:50%;height:100%;background:var(--open-line);border-radius:999px"></div>
          </div>
        </div>
        <div style="font-size:12px;color:var(--ink-3);margin-top:4px">Day 7 of 90 · Rp20M saved</div>
      </div>
    </div>

    <div style="display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap">
      <!-- Table Card -->
      <div class="card-clean" style="flex:1;min-width:320px;padding:0;overflow:hidden">
        <div style="display:grid;grid-template-columns:2.5fr 1fr 24px 1.5fr;background:var(--surface-2);padding:10px 16px;font-family:var(--font-ui);font-size:11px;font-weight:700;color:var(--ink-3)">
          <span>Path</span>
          <span>Day 0</span>
          <span></span>
          <span>Now</span>
        </div>
        <!-- Row 1: Fixed-price brand audit (OPENED) -->
        <div style="display:grid;grid-template-columns:2.5fr 1fr 24px 1.5fr;padding:14px 16px;background:var(--open-soft);border-top:1px solid var(--open-border);border-bottom:1px solid var(--open-border);align-items:center">
          <div>
            <strong>Fixed-price brand audit</strong>
            <div style="font-size:12px;color:var(--open-fg)">Opened · both conditions met</div>
          </div>
          <span class="status-pill not_yet">NOT YET</span>
          <span style="color:var(--open-fg);font-weight:700">→</span>
          <span class="status-pill open">OPEN</span>
        </div>
        <!-- Row 2: Warm network -->
        <div style="display:grid;grid-template-columns:2.5fr 1fr 24px 1.5fr;padding:12px 16px;border-bottom:1px solid var(--border);align-items:center">
          <div>
            <span>Advising people you know</span>
            <div style="font-size:11.5px;color:var(--ink-3)">Still working · current path</div>
          </div>
          <span class="status-pill open">OPEN</span>
          <span>→</span>
          <span class="status-pill open">OPEN</span>
        </div>
        <!-- Row 3: Part-time marketing lead -->
        <div style="display:grid;grid-template-columns:2.5fr 1fr 24px 1.5fr;padding:12px 16px;border-bottom:1px solid var(--border);align-items:center">
          <div>
            <span>Part-time marketing lead</span>
            <div style="font-size:11.5px;color:var(--ink-3)">Needs 2 audits done</div>
          </div>
          <span class="status-pill not_yet">NOT YET</span>
          <span>→</span>
          <span class="status-pill not_yet">NOT YET</span>
        </div>
        <!-- Row 4: Agency -->
        <div style="display:grid;grid-template-columns:2.5fr 1fr 24px 1.5fr;padding:12px 16px;border-bottom:1px solid var(--border);align-items:center">
          <div>
            <span>Freelancing for agencies</span>
            <div style="font-size:11.5px;color:var(--ink-3)">Nothing new yet</div>
          </div>
          <span class="status-pill test_first">TEST FIRST</span>
          <span>→</span>
          <span class="status-pill test_first">TEST FIRST</span>
        </div>
        <!-- Row 5: Paid Ads -->
        <div style="display:grid;grid-template-columns:2.5fr 1fr 24px 1.5fr;padding:12px 16px;align-items:center">
          <div>
            <span>Paid LinkedIn ads</span>
            <div style="font-size:11.5px;color:var(--ink-3)">Clients came from people you know. More reach won't help yet.</div>
          </div>
          <span class="status-pill stop">STOP</span>
          <span>→</span>
          <span class="status-pill stop">STOP</span>
        </div>
      </div>

      <!-- Side Card: Why opened -->
      <div class="card-clean" style="width:380px;flex-shrink:0">
        <div class="section-meta-label">Why the audit path opened</div>
        <div style="display:flex;flex-direction:column;gap:12px;margin-top:12px;font-size:13.5px;line-height:1.55">
          <div style="display:flex;align-items:flex-start;gap:8px">
            <span style="color:var(--open-fg);font-weight:700">✓</span>
            <div><strong>At least 1 paying client:</strong> Sari signed a 1-month brand audit, Rp15M</div>
          </div>
          <div style="display:flex;align-items:flex-start;gap:8px">
            <span style="color:var(--open-fg);font-weight:700">✓</span>
            <div><strong>1 more request for the same work:</strong> another contact asked what an audit costs</div>
          </div>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;margin:14px 0">
          <span class="evidence-chip">Sari's signed audit</span>
          <span class="evidence-chip">The price question</span>
        </div>
        <div style="font-size:12.5px;color:var(--ink-2);background:var(--surface-2);border-radius:8px;padding:10px 12px;line-height:1.5">
          Two people asking for the same thing is the first sign it can become a package you sell again and again, not a one-off favor.
        </div>
      </div>
    </div>

    <!-- What to do next section -->
    <div style="margin-top:10px">
      <div class="section-meta-label mb-8">What do you want to do next?</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
        <!-- Choice 1: DarkCard Recommended -->
        <div class="card-dark" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
              <span class="status-pill open" style="background:var(--open-line);color:var(--on-ink);border:none">RECOMMENDED · NEW PATH</span>
            </div>
            <h3 style="font-family:var(--font-ui);font-size:18px;font-weight:700;margin-bottom:8px">Switch to Fixed-price brand audit</h3>
            <p style="font-size:13.5px;color:var(--border-strong);line-height:1.55">Turn the audit you just sold into a fixed 2-week package at Rp15M, and send it to the contact who asked about your price.</p>
          </div>
          <div style="margin-top:20px">
            <button class="btn-primary" style="background:var(--surface);color:var(--ink);width:100%" onclick="applyPathFrom06a('audit')">Take this path →</button>
          </div>
        </div>

        <!-- Choice 2: Keep going -->
        <div class="card-clean" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
              <span class="section-meta-label">Keep going</span>
            </div>
            <h3 style="font-family:var(--font-ui);font-size:18px;font-weight:700;margin-bottom:8px">Stay on Advising people you know</h3>
            <p style="font-size:13.5px;color:var(--ink-2);line-height:1.55">Reach the rest of the people you know first, then build the package. Slower, but builds more evidence before you commit.</p>
          </div>
          <div style="margin-top:20px">
            <button class="btn-secondary" style="width:100%" onclick="applyPathFrom06a('warm')">Stay on this path</button>
          </div>
        </div>
      </div>
      <div style="font-size:12px;color:var(--ink-3);margin-top:10px;text-align:center">
        Either way, the next week starts from here and your history is kept.
      </div>
    </div>
  </div>`;
  return renderAppShell('map', 'Map updated', content);
}

// Turn the check-in form into a history record
function checkInRecordFromForm(rp, paths) {
  const cd = STORE.checkInData || {};
  const outcome = STORE.checkInOutcome || 'worked';
  const paid = outcome === 'worked' ? (cd.paidRaw || 15) : 0;
  const titles = {
    worked: paid ? `Paid client · Rp${paid}M` : 'It worked',
    mixed: 'Interested, but no one paid yet',
    none: 'No replies this week'
  };
  return {
    outcome,
    contacted: Number(cd.contacted) || 0,
    replies: Number(cd.replies) || 0,
    calls: Number(cd.calls) || 0,
    paid,
    rp,
    saved: useRoadmapStore.getState().moneySaved,
    paths,
    title: titles[outcome] || 'Check-in saved'
  };
}

function applyPathFrom06a(pathChoice) {
  const rp = (STORE.checkInData && STORE.checkInData.paidRaw) || 15;
  useRoadmapStore.getState().recordCheckIn(checkInRecordFromForm(rp, ['warm', 'audit']), pathChoice || 'audit');
  renderScreen('04');
}

function applyPivotFrom06b() {
  useRoadmapStore.getState().recordCheckIn(checkInRecordFromForm(0, ['warm']), 'warm_retest');
  renderScreen('04');
}

function applyPivotFrom12() {
  useRoadmapStore.getState().recordCheckIn(checkInRecordFromForm(0, ['warm']), 'warm_starter');
  renderScreen('04');
}

/* ── Screen 06b · Map adjusted - No Response ────────────────────────────── */
function screen06b() {
  const content = `
  <div style="padding:40px 56px;display:flex;flex-direction:column;gap:28px">
    <div>
      <div class="section-meta-label">Map adjusted from your Day 7 check-in</div>
      <h1 class="serif-heading" style="font-size:36px">No replies this week. That's evidence too.</h1>
      <p style="font-size:14.5px;color:var(--ink-2);margin-top:6px">Your goal hasn't changed, and neither has what we know about your expertise. What changes is how we test the offer.</p>
    </div>

    <div style="display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap">
      <!-- Left Column: What We Learned + Plan -->
      <div style="flex:1;min-width:320px;display:flex;flex-direction:column;gap:20px">
        <div class="card-clean">
          <div class="section-meta-label">What we learned</div>
          <div style="display:flex;gap:24px;margin:12px 0 16px">
            <div>
              <div style="font-size:24px;font-weight:700">7</div>
              <div style="font-size:12px;color:var(--ink-3)">contacts reached</div>
            </div>
            <div>
              <div style="font-size:24px;font-weight:700;color:var(--ink-muted)">0</div>
              <div style="font-size:12px;color:var(--ink-3)">replies in 7 days</div>
            </div>
          </div>
          <p style="font-size:14px;color:var(--ink);line-height:1.55">
            Your two paid projects still prove people pay for your expertise. So the silence most likely points at the <strong>message</strong> (too long, or no clear question), not at you.
          </p>
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:14px">
            <span class="evidence-chip">0 of 7 replied</span>
            <span class="evidence-chip">Your 2 paid projects</span>
          </div>
        </div>

        <!-- Plan Card -->
        <div class="card-dark">
          <div class="section-meta-label" style="color:var(--border-strong)">Next 7 days</div>
          <h3 style="font-family:var(--font-ui);font-size:20px;font-weight:700;margin:6px 0 4px">Try again, smaller and more personal.</h3>
          <p style="font-size:13.5px;color:var(--border);line-height:1.5;margin-bottom:18px">Same people, a different ask. Success: 1 conversation booked.</p>
          
          <div style="display:flex;flex-direction:column;gap:12px;font-size:13.5px;border-top:1px solid var(--ink-2b);padding-top:14px">
            <div style="display:flex;justify-content:space-between">
              <span>Day 1–2: Call the 2 contacts who asked. 10 minutes each, nothing attached</span>
            </div>
            <div style="display:flex;justify-content:space-between">
              <span>Day 3–5: Ask one question: “What would make 20 min on your brand worth it?”</span>
            </div>
            <div style="display:flex;justify-content:space-between">
              <span>Day 7: Report what you heard, word for word if you can</span>
            </div>
          </div>

          <div style="display:flex;gap:12px;margin-top:22px">
            <button class="btn-primary" style="background:var(--surface);color:var(--ink)" onclick="applyPivotFrom06b()">Start trying again →</button>
            <button class="btn-secondary" style="border-color:var(--ink-2b);color:var(--on-ink)" onclick="renderScreen('07')">See your map</button>
          </div>
        </div>
      </div>

      <!-- Right Column: What Changed On Your Map -->
      <div class="card-clean" style="width:400px;flex-shrink:0">
        <div class="section-meta-label">What changed on your map</div>
        <div style="display:flex;flex-direction:column;gap:14px;margin-top:14px">
          <div style="padding:10px 12px;background:var(--open-soft);border-radius:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <strong>Advising people you know</strong>
              <span class="status-pill open">OPEN · TRYING AGAIN</span>
            </div>
            <div style="font-size:12px;color:var(--open-fg);margin-top:4px">Adjusted: shorter message, one direct question, call instead of text</div>
          </div>

          <div style="padding:10px 12px;background:var(--surface-2);border-radius:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>Freelancing for agencies</span>
              <span class="status-pill test_first">TEST FIRST</span>
            </div>
            <div style="font-size:12px;color:var(--ink-3);margin-top:4px">Moved up: the next thing to test if this try stays quiet</div>
          </div>

          <div style="padding:10px 12px;background:var(--surface-2);border-radius:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>Fixed-price brand audit</span>
              <span class="status-pill not_yet">NOT YET</span>
            </div>
            <div style="font-size:12px;color:var(--ink-3);margin-top:4px">Unchanged · still needs a first paying client</div>
          </div>

          <div style="padding:10px 12px;background:var(--stop-soft);border:1px solid var(--stop-border);border-radius:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span style="color:var(--stop-fg);font-weight:600">Paid LinkedIn ads</span>
              <span class="status-pill stop">STOP</span>
            </div>
            <div style="font-size:12px;color:var(--stop-fg);margin-top:4px">Still stopped: if people who know you didn't reply, strangers won't fix the message</div>
          </div>
        </div>
      </div>
    </div>
  </div>`;
  return renderAppShell('map', 'Map adjusted', content);
}

/* ── Screen 12 · Map adjusted · Mixed Result ───────────────────────────── */
function screen12() {
  const content = `
  <div style="padding:40px 56px;display:flex;flex-direction:column;gap:28px">
    <div>
      <div class="section-meta-label">Map adjusted from your Day 7 check-in · mixed result</div>
      <h1 class="serif-heading" style="font-size:36px">People are interested. The first step is too big.</h1>
      <p style="font-size:14.5px;color:var(--ink-2);margin-top:6px">Four replies and two calls tell us the need is real. No one said yes yet because the first commitment feels too large. So we make it smaller, not cheaper.</p>
    </div>

    <div style="display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap">
      <!-- Left Column: What We Learned + Plan -->
      <div style="flex:1;min-width:320px;display:flex;flex-direction:column;gap:20px">
        <div class="card-clean">
          <div class="section-meta-label">What we learned</div>
          <div style="display:flex;gap:24px;margin:12px 0 16px">
            <div>
              <div style="font-size:24px;font-weight:700">4 / 7</div>
              <div style="font-size:12px;color:var(--ink-3)">replied</div>
            </div>
            <div>
              <div style="font-size:24px;font-weight:700">2</div>
              <div style="font-size:12px;color:var(--ink-3)">calls held</div>
            </div>
            <div>
              <div style="font-size:24px;font-weight:700;color:var(--ink-muted)">0</div>
              <div style="font-size:12px;color:var(--ink-3)">said yes and paid</div>
            </div>
          </div>

          <div style="border:1px solid var(--border);border-radius:8px;padding:10px 14px;margin:12px 0">
            <blockquote style="font-style:italic;font-size:14px;color:var(--ink);line-height:1.5">
              “Interesting, but it feels too big for a first project. Is there a smaller version?”
            </blockquote>
            <div style="font-size:11.5px;color:var(--ink-3);margin-top:4px">From your check-in notes · said by both people you called</div>
          </div>

          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:14px">
            <span class="evidence-chip">4 of 7 replied</span>
            <span class="evidence-chip">Both asked for a smaller start</span>
          </div>
        </div>

        <!-- Plan Card -->
        <div class="card-clean">
          <div class="section-meta-label">Next 7 days</div>
          <h3 style="font-family:var(--font-ui);font-size:20px;font-weight:700;margin:6px 0 4px">Offer a smaller first step.</h3>
          <p style="font-size:13.5px;color:var(--ink-2);line-height:1.5;margin-bottom:18px">Success: 1 of the 2 says yes to the starter version.</p>
          
          <div style="display:flex;flex-direction:column;gap:12px;font-size:13.5px">
            <div style="display:flex;justify-content:space-between">
              <span>Day 1–2: Cut your offer to a 2-week starter version at Rp7.5M</span>
            </div>
            <div style="display:flex;justify-content:space-between">
              <span>Day 3–5: Send it to the 2 people you called, referencing what they asked for</span>
            </div>
            <div style="display:flex;justify-content:space-between">
              <span>Day 7: Report their answer</span>
            </div>
          </div>

          <div class="card-danger" style="margin-top:16px;padding:14px">
            <div class="section-meta-label" style="color:var(--stop-fg)">What not to do</div>
            <div style="font-size:13px;color:var(--ink);line-height:1.5;margin-top:4px">
              Don't cut your price in half. They asked for a smaller start, not a lower price. A discount now sets the price for every project after.
            </div>
          </div>

          <div style="display:flex;gap:12px;margin-top:22px">
            <button class="btn-primary" onclick="applyPivotFrom12()">Start the next week (smaller offer) →</button>
            <button class="btn-secondary" onclick="renderScreen('07')">See your map</button>
          </div>
        </div>
      </div>

      <!-- Right Column: What Changed On Your Map -->
      <div class="card-clean" style="width:400px;flex-shrink:0">
        <div class="section-meta-label">What changed on your map</div>
        <div style="display:flex;flex-direction:column;gap:14px;margin-top:14px">
          <div style="padding:10px 12px;background:var(--open-soft);border-radius:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <strong>Advising people you know</strong>
              <span class="status-pill open">OPEN · ADJUSTED</span>
            </div>
            <div style="font-size:12px;color:var(--open-fg);margin-top:4px">Adjusted: offer a smaller first step to the 2 people you called</div>
          </div>

          <div style="padding:10px 12px;background:var(--surface-2);border-radius:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>Fixed-price brand audit</span>
              <span class="status-pill not_yet">NOT YET · 1 OF 2</span>
            </div>
            <div style="font-size:12px;color:var(--ink-3);margin-top:4px">Closer: the same request came twice. Still needs a first paying client</div>
          </div>

          <div style="padding:10px 12px;background:var(--surface-2);border-radius:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>Freelancing for agencies</span>
              <span class="status-pill test_first">TEST FIRST</span>
            </div>
            <div style="font-size:12px;color:var(--ink-3);margin-top:4px">Nothing new yet</div>
          </div>

          <div style="padding:10px 12px;background:var(--stop-soft);border:1px solid var(--stop-border);border-radius:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span style="color:var(--stop-fg);font-weight:600">Paid LinkedIn ads</span>
              <span class="status-pill stop">STOP</span>
            </div>
            <div style="font-size:12px;color:var(--stop-fg);margin-top:4px">Still stopped: you already have interested people. More reach isn't what's missing. The first yes is.</div>
          </div>
        </div>
      </div>
    </div>
  </div>`;
  return renderAppShell('map', 'Map adjusted', content);
}

/* Screens 07b/07c (v9 persona maps Rina/Arif) were removed in the 2026-10-15 legacy cleanup —
   only reachable via 'v9:07b'/'v9:07c'. Study persona maps now go through the Maps destination
   demo mode (persona widget). Demo button 13 "Update my diagnosis" is redirected to the V11_ALIAS alias. */

/* ── Screen 10 · Same Question, Opposite Answers (Contrast Demo) ────────── */
function screen10() {
  return `
  <div style="max-width:1296px;margin:0 auto;padding:48px 32px 80px;display:flex;flex-direction:column;gap:36px">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <div class="section-meta-label">Same goal · same question · opposite answers</div>
      <button class="btn-secondary btn-sm" onclick="renderScreen('17')">← Back to Diagnosis</button>
    </div>

    <!-- Quote Card -->
    <div class="card-clean" style="text-align:center;padding:36px 24px">
      <div class="serif-heading" style="font-size:32px;line-height:1.35;max-width:820px;margin:0 auto">
        “Should I spend Rp10M on LinkedIn ads to reach Rp30M a month?”
      </div>
      <div style="font-size:13px;color:var(--ink-3);margin-top:10px;font-family:var(--font-ui)">
        Asked by both, word for word
      </div>
    </div>

    <!-- Side-by-Side Grid -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:28px">
      <!-- Dimas Card -->
      <div class="card-clean" style="display:flex;flex-direction:column;gap:20px;padding:28px">
        <div style="display:flex;align-items:center;gap:12px">
          <div style="width:40px;height:40px;border-radius:50%;background:var(--ink);color:var(--on-ink);display:flex;align-items:center;justify-content:center;font-weight:700">D</div>
          <div>
            <div style="font-family:var(--font-ui);font-weight:700;font-size:16px">Dimas A.</div>
            <div style="font-size:12.5px;color:var(--ink-2)">Left a corporate job 2 months ago · Rp0 regular income</div>
          </div>
        </div>

        <div>
          <div class="section-meta-label mb-8">What the evidence shows</div>
          <div style="display:flex;flex-direction:column;gap:8px;font-size:13.5px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>✓ 2 one-off paid projects</span>
              <span class="evidence-chip">Payment</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>✕ No written offer or price</span>
              <span class="evidence-chip">Action</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>✕ 0 buyers contacted in 30 days</span>
              <span class="evidence-chip">Action</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>? “Ads will bring me clients”</span>
              <span class="tag-chip assumption">Assumption</span>
            </div>
          </div>
        </div>

        <div>
          <div class="section-meta-label mb-8">Verdict on paid ads</div>
          <div class="spectrum-grid">
            <div class="spectrum-cell active-stop">STOP</div>
            <div class="spectrum-cell">NOT YET</div>
            <div class="spectrum-cell">TEST FIRST</div>
            <div class="spectrum-cell">GO SMALL</div>
            <div class="spectrum-cell">GO</div>
            <div class="spectrum-cell">SCALE</div>
          </div>
        </div>

        <!-- Result Box -->
        <div style="background:var(--stop-soft);border:1px solid var(--stop-border);border-radius:12px;padding:18px">
          <h4 style="font-family:var(--font-ui);font-size:16px;font-weight:700;color:var(--stop-fg);margin-bottom:6px">Don't run ads yet.</h4>
          <p style="font-size:13.5px;color:var(--ink);line-height:1.5;margin-bottom:10px">
            Ads would send strangers to an offer that doesn't exist. Instead: write a one-page offer and send it to the 2 people who asked.
          </p>
          <div style="font-family:var(--font-ui);font-size:12px;font-weight:700;color:var(--stop-fg)">Protects Rp10M</div>
        </div>
      </div>

      <!-- Arif Card -->
      <div class="card-clean" style="display:flex;flex-direction:column;gap:20px;padding:28px">
        <div style="display:flex;align-items:center;gap:12px">
          <div style="width:40px;height:40px;border-radius:50%;background:var(--open-line);color:var(--on-ink);display:flex;align-items:center;justify-content:center;font-weight:700">A</div>
          <div>
            <div style="font-family:var(--font-ui);font-weight:700;font-size:16px">Arif S.</div>
            <div style="font-size:12.5px;color:var(--ink-2)">Runs a brand studio · Rp18M / month</div>
          </div>
        </div>

        <div>
          <div class="section-meta-label mb-8">What the evidence shows</div>
          <div style="display:flex;flex-direction:column;gap:8px;font-size:13.5px">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>✓ 4 active clients, Rp4.5M each per month</span>
              <span class="evidence-chip">Payment</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>✓ 2 returning clients asked for an audit</span>
              <span class="evidence-chip">Action</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>✓ Fixed-price audit package written</span>
              <span class="evidence-chip">Action</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <span>○ Never tried paid ads</span>
              <span class="evidence-chip">Missing</span>
            </div>
          </div>
        </div>

        <div>
          <div class="section-meta-label mb-8">Verdict on paid ads</div>
          <div class="spectrum-grid">
            <div class="spectrum-cell">STOP</div>
            <div class="spectrum-cell">NOT YET</div>
            <div class="spectrum-cell active-test">TEST FIRST</div>
            <div class="spectrum-cell">GO SMALL</div>
            <div class="spectrum-cell">GO</div>
            <div class="spectrum-cell">SCALE</div>
          </div>
        </div>

        <!-- Result Box -->
        <div style="background:var(--test-soft);border:1px solid var(--test-border);border-radius:12px;padding:18px">
          <h4 style="font-family:var(--font-ui);font-size:16px;font-weight:700;color:var(--test-fg);margin-bottom:6px">Test it with Rp2M, not Rp10M.</h4>
          <p style="font-size:13.5px;color:var(--ink);line-height:1.5;margin-bottom:10px">
            People already pay for your offer, but you don't know yet if ads work for it. Run a small test with a spending limit. It stops by itself on Day 14 if no serious buyer books a call.
          </p>
          <div style="font-family:var(--font-ui);font-size:12px;font-weight:700;color:var(--test-fg)">Puts Rp2M at risk, not Rp10M</div>
        </div>
      </div>
    </div>

    <!-- Footer Quote -->
    <div style="text-align:center;border-top:1px solid var(--border);padding-top:32px">
      <div class="serif-heading" style="font-size:24px">We don't judge an action on its own. We judge it against your situation.</div>
      <div style="display:flex;gap:12px;justify-content:center;margin-top:20px">
        <button class="btn-primary" onclick="setPersona('dimas')">Open Dimas's map →</button>
        <button class="btn-secondary" onclick="setPersona('arif')">Open Arif's path map →</button>
      </div>
    </div>
  </div>`;
}

/* ── Screen 13 · Provisional Diagnosis (Persona Rina) ──────────────────── */
function screen13() {
  const q1 = STORE.rinaQ1;
  const q2 = STORE.rinaQ2;
  const count = (q1 !== null ? 1 : 0) + (q2 !== null ? 1 : 0);
  const ready = count === 2;

  return `<div class="full-canvas" style="background:var(--surface)">
    ${renderOnboardingTopBar(2, 'Save & exit', "renderScreen('01')")}
    <div style="max-width:1040px;margin:0 auto;padding:48px 32px 96px;display:flex;flex-direction:column;gap:32px">
      <div>
        <div style="display:flex;align-items:center;gap:8px;font-family:var(--font-ui);font-size:13px;margin-bottom:8px">
          <span class="section-meta-label">Your income diagnosis</span>
          <span>·</span>
          <span class="status-pill not_yet" style="background:var(--notyet-bg-2);color:var(--notyet-fg);border:1px solid var(--notyet-border)">NOT FINAL YET</span>
        </div>
        <h1 class="serif-heading" style="font-size:40px">Here's our best read so far. It isn't certain yet.</h1>
        <p style="font-size:16px;color:var(--ink-2);margin-top:10px;max-width:760px">
          Three of your five answers had no numbers, so three explanations are still close. We'd rather tell you that than guess. Two quick answers would separate them.
        </p>
      </div>

      <!-- 3 Explanations Bars Card -->
      <div class="card-clean">
        <div class="section-meta-label mb-8">Three explanations, still close</div>
        <div style="display:flex;flex-direction:column;gap:12px;margin:14px 0">
          <div>
            <div style="display:flex;justify-content:space-between;font-size:13.5px;font-weight:600;margin-bottom:4px">
              <span>1. No one has asked to work with you yet</span>
              <span>41%</span>
            </div>
            <div style="height:8px;background:var(--surface-2);border-radius:999px;overflow:hidden">
              <div style="width:41%;height:100%;background:var(--ink);border-radius:999px"></div>
            </div>
          </div>

          <div>
            <div style="display:flex;justify-content:space-between;font-size:13.5px;font-weight:600;margin-bottom:4px">
              <span>2. Your skill isn't framed as a service</span>
              <span>33%</span>
            </div>
            <div style="height:8px;background:var(--surface-2);border-radius:999px;overflow:hidden">
              <div style="width:33%;height:100%;background:var(--ink-3);border-radius:999px"></div>
            </div>
          </div>

          <div>
            <div style="display:flex;justify-content:space-between;font-size:13.5px;font-weight:600;margin-bottom:4px">
              <span>3. You're aiming at the wrong buyers</span>
              <span>26%</span>
            </div>
            <div style="height:8px;background:var(--surface-2);border-radius:999px;overflow:hidden">
              <div style="width:26%;height:100%;background:var(--ink-muted);border-radius:999px"></div>
            </div>
          </div>
        </div>
        <div style="font-size:12.5px;color:var(--ink-3);line-height:1.5;border-top:1px solid var(--border);padding-top:10px">
          We only name the main problem when one clearly stands out. Right now the top two are only 8 points apart. That's too close to act on.
        </div>
      </div>

      <!-- Interactive 2 Questions Card -->
      <div class="card-clean" style="max-width:640px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
          <div class="section-meta-label">Two answers that would settle it</div>
          <span style="font-family:var(--font-ui);font-size:12px;font-weight:700;color:${ready ? 'var(--open-fg)' : 'var(--ink-3)'}">
            ${count} of 2 answered
          </span>
        </div>

        <!-- Question 1 -->
        <div style="margin-bottom:20px">
          <label style="font-size:14px;font-weight:600;display:block;margin-bottom:8px">
            1. In the last 3 months, how many people asked about working with you?
          </label>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="example-chip-box ${q1 === '0' ? 'selected' : ''}" style="${q1 === '0' ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="selectRinaAnswer(1, '0')">0</button>
            <button class="example-chip-box ${q1 === '1-2' ? 'selected' : ''}" style="${q1 === '1-2' ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="selectRinaAnswer(1, '1-2')">1–2</button>
            <button class="example-chip-box ${q1 === '3-5' ? 'selected' : ''}" style="${q1 === '3-5' ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="selectRinaAnswer(1, '3-5')">3–5</button>
            <button class="example-chip-box ${q1 === '6+' ? 'selected' : ''}" style="${q1 === '6+' ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="selectRinaAnswer(1, '6+')">6 or more</button>
          </div>
        </div>

        <!-- Question 2 -->
        <div style="margin-bottom:20px">
          <label style="font-size:14px;font-weight:600;display:block;margin-bottom:8px">
            2. Has anyone paid you for this skill outside a salary?
          </label>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="example-chip-box ${q2 === 'never' ? 'selected' : ''}" style="${q2 === 'never' ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="selectRinaAnswer(2, 'never')">Never</button>
            <button class="example-chip-box ${q2 === 'once' ? 'selected' : ''}" style="${q2 === 'once' ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="selectRinaAnswer(2, 'once')">Once</button>
            <button class="example-chip-box ${q2 === 'few' ? 'selected' : ''}" style="${q2 === 'few' ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="selectRinaAnswer(2, 'few')">A few times</button>
            <button class="example-chip-box ${q2 === 'regular' ? 'selected' : ''}" style="${q2 === 'regular' ? 'background:var(--ink);color:var(--on-ink);border-color:var(--ink)' : ''}" onclick="selectRinaAnswer(2, 'regular')">Regularly</button>
          </div>
        </div>

        <div style="display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--border);padding-top:14px">
          <span style="font-size:12px;color:var(--ink-3)">Ranges are fine. Exact numbers aren't needed.</span>
          <button class="btn-primary" ${!ready ? 'disabled style="opacity:0.5;cursor:not-allowed"' : ''} onclick="renderScreen('07b')">
            Update my diagnosis →
          </button>
        </div>
      </div>

      <!-- Safe to Say Already -->
      <div class="card-danger">
        <div class="section-meta-label" style="color:var(--stop-fg)">Safe to say already</div>
        <p style="font-size:14px;color:var(--ink);line-height:1.55;margin-top:6px">
          Whichever explanation wins, these still hold: <strong>don't lease an office, don't run ads, and don't register a company yet.</strong> None of them can create your first paying client.
        </p>
      </div>

      <!-- Rather start now -->
      <div class="card-clean" style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <strong>Rather start now?</strong>
          <div style="font-size:13px;color:var(--ink-2)">Begin with a small test that helps under all three explanations.</div>
        </div>
        <button class="btn-secondary" onclick="renderScreen('07b')">Start with a test →</button>
      </div>
    </div>
  </div>`;
}

function selectRinaAnswer(q, val) {
  if (q === 1) STORE.rinaQ1 = val;
  if (q === 2) STORE.rinaQ2 = val;
  renderScreen('13');
}

/* ── Screen 14 · Welcome back (Today, Returning State) ─────────────────── */
function screen14() {
  const wbRs = useRoadmapStore.getState();
  const wbTl = getTimeline();
  const missed = wbRs.history.slice().reverse().find(r => r.outcome === 'missed');
  const missedDay = missed ? missed.day : 7;
  const wbStep = wbRs.steps[wbRs.currentStep - 1];
  const opt = STORE.welcomeBackOption || 'busy';
  const timeline = STORE.welcomeBackTimeline || 90;

  const content = `
  <div style="padding:40px 56px;display:flex;flex-direction:column;gap:28px">
    <div>
      <div class="section-meta-label">${wbTl.day - missedDay + 5} day${wbTl.day - missedDay + 5 === 1 ? '' : 's'} since your last visit · Day ${missedDay} check-in missed</div>
      <h1 class="serif-heading" style="font-size:36px">Welcome back, Dimas. Let's start from where you are now.</h1>
    </div>

    <div style="display:flex;gap:28px;align-items:flex-start;flex-wrap:wrap">
      <!-- Left Column: Status Selector + Micro Action -->
      <div style="flex:1;min-width:320px;display:flex;flex-direction:column;gap:20px">
        <div class="card-clean">
          <div class="section-meta-label mb-8">Did anything happen since we last spoke?</div>
          <div style="font-size:13.5px;color:var(--ink-2);margin-bottom:14px">
            Your next step is “${wbStep.label}.”
          </div>

          <div style="display:flex;flex-direction:column;gap:10px">
            <div class="radio-card ${opt === 'results' ? 'selected' : ''}" onclick="setWelcomeBackOption('results')">
              <div class="radio-dot"></div>
              <div>
                <div style="font-family:var(--font-ui);font-weight:700;font-size:14px">Yes, I have results to report</div>
                ${opt === 'results' ? `
                <div style="font-size:13px;color:var(--open-fg);margin-top:4px">
                  Great. Log them now and your map updates straight away.
                  <div style="margin-top:8px"><button class="btn-primary btn-sm" onclick="renderScreen('05')">Report results →</button></div>
                </div>` : ''}
              </div>
            </div>

            <div class="radio-card ${opt === 'steps' ? 'selected' : ''}" onclick="setWelcomeBackOption('steps')">
              <div class="radio-dot"></div>
              <div>
                <div style="font-family:var(--font-ui);font-weight:700;font-size:14px">I did some steps, but no results yet</div>
                ${opt === 'steps' ? `
                <div style="font-size:13px;color:var(--ink-2);margin-top:4px">
                  That still counts. Tick what you did and we'll pick up from the next step.
                </div>` : ''}
              </div>
            </div>

            <div class="radio-card ${opt === 'busy' ? 'selected' : ''}" onclick="setWelcomeBackOption('busy')">
              <div class="radio-dot"></div>
              <div>
                <div style="font-family:var(--font-ui);font-weight:700;font-size:14px">Nothing yet, life got busy</div>
                ${opt === 'busy' ? `
                <div style="font-size:13px;color:var(--ink-2);margin-top:4px">
                  That's okay, and it happens to most people. Nothing is lost: your path is still open. We've shrunk this week to one 15-minute step.
                </div>` : ''}
              </div>
            </div>
          </div>
        </div>

        <!-- 15-Minute Micro Step Card -->
        ${opt !== 'results' ? `
        <div class="card-clean" style="border:2px solid var(--ink);padding:24px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
            <span class="section-meta-label" style="color:var(--ink)">This week, smaller · 15 minutes</span>
            <span class="status-pill open">ACTIVE</span>
          </div>
          <h3 style="font-family:var(--font-ui);font-size:20px;font-weight:700;margin-bottom:6px">Send one message, just to Sari.</h3>
          <p style="font-size:13.5px;color:var(--ink-2);line-height:1.55;margin-bottom:14px">
            No need to contact everyone. Just send this one message to get going again.
          </p>

          <div style="background:var(--surface-2);border:1px solid var(--border);border-radius:8px;padding:12px 14px;font-size:13.5px;line-height:1.55;margin-bottom:14px">
            “Hi Sari, sorry it took me a while to get back to you. I have started my brand strategy business. Could I send you a one-page summary?”
          </div>

          <div style="display:flex;gap:10px">
            <button class="btn-primary btn-sm" onclick="copyTodayMsg(this)">Copy message</button>
            <button class="btn-secondary btn-sm" onclick="renderScreen('05')">Mark as done</button>
          </div>
        </div>` : ''}
      </div>

      <!-- Right Column: Timeline Adjustment & Safety -->
      <div style="width:380px;display:flex;flex-direction:column;gap:18px;flex-shrink:0">
        <!-- Timeline Card -->
        <div class="card-clean">
          <div class="section-meta-label">Your timeline</div>
          <p style="font-size:13.5px;color:var(--ink-2);margin:6px 0 12px">
            Goal stays at Rp30M a month. Do you want to keep the deadline, or give yourself more room?
          </p>
          <div style="display:flex;gap:10px">
            <button class="card-clean" style="flex:1;padding:10px;text-align:center;border:1.5px solid ${timeline === 90 ? 'var(--ink)' : 'var(--border)'}" onclick="setWelcomeBackTimeline(90)">
              <div style="font-weight:700;font-size:13px">Keep Day 90</div>
              <div style="font-size:11px;color:var(--ink-3)">${wbTl.daysLeft} days left</div>
            </button>
            <button class="card-clean" style="flex:1;padding:10px;text-align:center;border:1.5px solid ${timeline === 120 ? 'var(--ink)' : 'var(--border)'}" onclick="setWelcomeBackTimeline(120)">
              <div style="font-weight:700;font-size:13px">Move to Day 120</div>
              <div style="font-size:11px;color:var(--ink-3)">${wbTl.daysLeft + 30} days left</div>
            </button>
          </div>
          <div style="font-size:11.5px;color:var(--ink-3);margin-top:8px">
            Moving the deadline changes the weekly pace, not the paths.
          </div>
        </div>

        <!-- WhatsApp Reminder Card -->
        <div class="card-clean">
          <div class="section-meta-label">Stay on track</div>
          <label style="display:flex;align-items:center;gap:8px;font-size:13px;margin-top:8px;cursor:pointer">
            <input type="checkbox" checked style="accent-color:var(--ink)">
            <span>WhatsApp reminder · Monday step & Sunday check-in</span>
          </label>
        </div>

        <!-- What Didn't Change -->
        <div class="card-soft-green">
          <div class="section-meta-label" style="color:var(--open-fg)">What didn't change</div>
          <div style="font-size:13px;color:var(--ink);line-height:1.5;margin-top:6px">
            Advising people you know is still open, your answers are saved, and the Rp20M you saved is still safe.
          </div>
        </div>
      </div>
    </div>
  </div>`;
  return renderAppShell('activity', 'Welcome back', content);
}

function setWelcomeBackOption(val) {
  STORE.welcomeBackOption = val;
  renderScreen('14');
}

function setWelcomeBackTimeline(days) {
  STORE.welcomeBackTimeline = days;
  renderScreen('14');
}

/* ── Screen 15 · Safety First (Persona Bayu) ───────────────────────────── */
function screen15() {
  return `<div class="full-canvas" style="background:var(--surface)">
    ${renderOnboardingTopBar(2, 'Back', "renderScreen('01')")}
    <div style="max-width:1080px;margin:0 auto;padding:48px 32px 96px;display:flex;flex-direction:column;gap:32px">
      <div>
        <div style="display:flex;align-items:center;gap:8px;font-family:var(--font-ui);font-size:13px;margin-bottom:8px">
          <span class="section-meta-label">Your income diagnosis</span>
          <span>·</span>
          <span class="status-pill stop" style="background:var(--ink);color:var(--on-ink);border:none">SAFETY FIRST</span>
        </div>
        <h1 class="serif-heading" style="font-size:40px">Before growing a business, let's protect your next 60 days.</h1>
        <p style="font-size:16px;color:var(--ink-2);margin-top:10px;max-width:760px">
          You told us your savings cover about 5 weeks of essentials. At that point, the biggest risk isn't a wrong move. It's waiting months for a new business to start paying.
        </p>
      </div>

      <!-- 3-Column Grid -->
      <div style="display:grid;grid-template-columns:1fr 1.25fr 1fr;gap:20px">
        <!-- Col 1: Where you are -->
        <div class="card-clean" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div class="section-meta-label">Where you are</div>
            <div style="font-size:28px;font-weight:700;color:var(--stop-fg);margin:8px 0 4px">≈ 5 weeks</div>
            <div style="font-size:12.5px;color:var(--ink-3);margin-bottom:14px">before your savings run out</div>
            <div style="display:flex;flex-direction:column;gap:8px;font-size:13px;color:var(--ink-2);border-top:1px solid var(--border);padding-top:12px">
              <div>• Savings: Rp6M total</div>
              <div>• Essentials: ~Rp5M a month</div>
              <div>• 8 years as a brand designer</div>
              <div>• Goal: Rp25M / month from consulting</div>
            </div>
          </div>
        </div>

        <!-- Col 2: Recommendation (DarkCard) -->
        <div class="card-dark" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div class="section-meta-label" style="color:var(--border-strong)">Our recommendation</div>
            <h3 style="font-family:var(--font-ui);font-size:18px;font-weight:700;margin:6px 0 10px">Get some income coming in first. Then build your business on top of it.</h3>
            <div style="display:flex;flex-direction:column;gap:8px;font-size:13.5px;color:var(--border)">
              <div>✓ <strong>A paid one-off design project</strong> from your network, invoiced within 2 weeks</div>
              <div>✓ <strong>A short contract or part-time role</strong> in your field for steady income</div>
            </div>
          </div>
          <div style="border-top:1px solid var(--ink-2b);padding-top:12px;font-size:12px;color:var(--ink-muted);margin-top:14px">
            Your consulting goal is paused, not deleted. It comes back once your savings cover 3 months.
          </div>
        </div>

        <!-- Col 3: Not Right Now (DangerCard) -->
        <div class="card-danger" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div class="section-meta-label" style="color:var(--stop-fg)">Not right now</div>
            <div style="display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--ink);margin:10px 0">
              <div>✕ Paid ads</div>
              <div>✕ Paid courses or coaching</div>
              <div>✕ Borrowing to fund business</div>
              <div>✕ Office or company registration</div>
            </div>
          </div>
          <div style="font-size:12px;color:var(--stop-fg);font-weight:600">
            Each one spends savings you can't replace yet.
          </div>
        </div>
      </div>

      <!-- Paths Table Re-ranked -->
      <div class="card-clean" style="padding:0;overflow:hidden">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 20px;background:var(--surface-2);border-bottom:1px solid var(--border)">
          <span class="section-meta-label" style="margin:0">Your paths, ranked by how fast they pay</span>
          <span style="font-size:12px;color:var(--ink-3)">Same map, safety rules first</span>
        </div>
        <div style="display:flex;flex-direction:column">
          <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 20px;border-bottom:1px solid var(--border)">
            <div>
              <strong>One-off project from your network</strong>
              <div style="font-size:12.5px;color:var(--open-fg)">Fastest cash: invoiced in about 2 weeks</div>
            </div>
            <span class="status-pill open">OPEN · RECOMMENDED</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 20px;border-bottom:1px solid var(--border)">
            <div>
              <strong>Contract or part-time role</strong>
              <div style="font-size:12.5px;color:var(--ink-2)">Steady monthly income to rebuild your savings</div>
            </div>
            <span class="status-pill open">OPEN</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 20px;border-bottom:1px solid var(--border)">
            <div>
              <strong>Monthly consulting clients</strong>
              <div style="font-size:12.5px;color:var(--ink-3)">Needs at least 3 months of savings to try safely</div>
            </div>
            <span class="status-pill not_yet">NOT YET</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 20px">
            <div>
              <strong>Paid ads</strong>
              <div style="font-size:12.5px;color:var(--stop-fg)">Spends savings before anything is proven</div>
            </div>
            <span class="status-pill stop">STOP</span>
          </div>
        </div>
      </div>

      <!-- Footer Disclaimer & CTAs -->
      <div style="display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--border);padding-top:20px;flex-wrap:wrap;gap:14px">
        <p style="font-size:12px;color:var(--ink-3);max-width:580px;line-height:1.5">
          Novaliners helps with business decisions; it isn't financial advice. If rent, debt payments or essentials are at risk, a financial counselor can help you plan the next few months.
        </p>
        <div style="display:flex;gap:12px">
          <button class="btn-secondary btn-sm" onclick="renderScreen('04')">Keep my original goal</button>
          <button class="btn-primary" onclick="renderScreen('04')">Set a 60-day cash goal →</button>
        </div>
      </div>
    </div>
  </div>`;
}

/* ── Screen 16 · Day 90 review (miss or success) ───────────────────────── */
function screen16() {
  const rs = useRoadmapStore.getState();
  if (!rs.ending) {
    return renderAppShell('journey', 'Day 90 review', `
    <div class="today-layout" style="grid-template-columns:minmax(0, 560px);justify-content:center;align-content:center">
      <div class="card-clean" style="padding:28px;text-align:center">
        <h1 class="serif-heading" style="font-size:28px">Your Day 90 review isn't ready yet.</h1>
        <p style="font-size:14px;color:var(--ink-2);margin:10px 0 16px">It opens after your last check-in. Use "Jump to Day 90" in the prototype menu to see it now.</p>
        <button class="btn-primary" onclick="simulateToDay90('miss')">Jump to Day 90 →</button>
      </div>
    </div>`);
  }
  const miss = rs.ending === 'miss';
  const goal = rs.goalRp;
  const h = rs.history;
  const paidRecords = h.filter(r => r.paid > 0);
  const paidTotal = Math.round(paidRecords.reduce((sum, r) => sum + r.paid, 0) * 10) / 10;
  const opened = rs.activePaths.filter(p => p !== 'warm').map(p => JOURNEY_PATH_NAMES[p]);
  const peak = Math.max(...h.map(r => r.rp));
  const quietWeeks = h.filter(r => r.outcome === 'none' || r.outcome === 'missed').length;
  const choice = STORE.endingChoice;

  const options = miss ? [
    { id: 'extend', title: 'Give it 30 more days', desc: `Keep the Rp${goal}M goal and move the deadline to Day 120. Same paths, same weekly rhythm.`, tag: 'Keeps the goal' },
    { id: 'lower', title: `Set the goal to Rp${Math.round((rs.earned + goal) / 2)}M for now`, desc: `A goal between where you are and where you aimed. Rp${goal}M stays as the next step after it.`, tag: 'More realistic' },
    { id: 'switch', title: 'Lead with the part-time marketing lead role', desc: 'Steadier monthly income than one-off audits. Put most of your 6 free hours here.', tag: 'Changes the path' }
  ] : [
    { id: 'hold', title: `Hold Rp${goal}M for 30 days`, desc: 'Prove the income is steady before you aim higher. Fewer new tests, more follow-through.', tag: 'RECOMMENDED' },
    { id: 'raise', title: `Aim for Rp${goal * 2}M next`, desc: 'A new 90-day goal. The map redraws from what already works.', tag: 'New goal' },
    { id: 'register', title: 'Register your company', desc: `You have ${paidRecords.length} paying clients, so the rule that held this back is met.`, tag: 'UNLOCKED' }
  ];

  const content = `
  <div style="padding:32px 48px 40px;display:flex;flex-direction:column;gap:20px;max-width:1120px;width:100%;margin:0 auto">
    <div>
      <div class="section-meta-label" style="color:${miss ? 'var(--notyet-fg)' : 'var(--open-fg)'}">Day 90 review · ${h.length} check-ins</div>
      <h1 class="serif-heading" style="font-size:34px;margin-top:4px">${miss ? `You reached Rp${rs.earned}M a month. Not Rp${goal}M yet.` : `You reached Rp${rs.earned}M a month. Goal done.`}</h1>
      <p style="font-size:15px;color:var(--ink-2);margin-top:8px;max-width:760px;line-height:1.55">${miss
        ? `That's Rp${goal - rs.earned}M a month short. It's also Rp${rs.earned}M more than Day 0, with Rp${rs.moneySaved}M still in the bank. Missing the date doesn't undo that. Here's what happened, and three honest ways forward.`
        : `From Rp0 to Rp${rs.earned}M a month in 90 days, with Rp${rs.moneySaved}M still in the bank. Here's what got you there, and what to do next.`}</p>
    </div>

    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px">
      <div class="card-clean" style="padding:16px 18px">
        <div class="section-meta-label">Monthly income</div>
        <div style="font-size:22px;font-weight:700;margin-top:4px">Rp${rs.earned}M</div>
        <div style="font-size:11.5px;color:var(--ink-3);margin-top:2px">Goal Rp${goal}M · peak Rp${peak}M</div>
      </div>
      <div class="card-clean" style="padding:16px 18px">
        <div class="section-meta-label">Clients who paid</div>
        <div style="font-size:22px;font-weight:700;margin-top:4px">${paidRecords.length}</div>
        <div style="font-size:11.5px;color:var(--ink-3);margin-top:2px">Rp${paidTotal}M in new payments</div>
      </div>
      <div class="card-clean" style="padding:16px 18px">
        <div class="section-meta-label">Paths opened</div>
        <div style="font-size:22px;font-weight:700;margin-top:4px">${opened.length}</div>
        <div style="font-size:11.5px;color:var(--ink-3);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${opened.join(' + ') || 'None'}</div>
      </div>
      <div class="card-clean" style="padding:16px 18px">
        <div class="section-meta-label">Money saved</div>
        <div style="font-size:22px;font-weight:700;margin-top:4px">Rp${rs.moneySaved}M</div>
        <div style="font-size:11.5px;color:var(--ink-3);margin-top:2px">Office and ads kept on hold</div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div class="card-clean" style="padding:20px 22px">
        <div class="section-meta-label" style="margin-bottom:10px">What worked</div>
        <ul style="margin:0;padding-left:18px;display:flex;flex-direction:column;gap:6px;font-size:13.5px;color:var(--ink-2);line-height:1.5">
          <li>People you already knew became your first ${Math.min(paidRecords.length, 2)} paying clients.</li>
          <li>A smaller first step turned "too big" into a yes.</li>
          <li>Testing ads with Rp2M instead of Rp10M kept Rp8M in the bank.</li>
          ${miss ? '' : '<li>The part-time marketing lead role added steady monthly income on top of audits.</li>'}
        </ul>
      </div>
      <div class="card-clean" style="padding:20px 22px">
        <div class="section-meta-label" style="margin-bottom:10px">${miss ? 'What held it back' : 'What to watch'}</div>
        <ul style="margin:0;padding-left:18px;display:flex;flex-direction:column;gap:6px;font-size:13.5px;color:var(--ink-2);line-height:1.5">
          ${miss ? `
          <li>Time, not demand: two open paths needed about 9 h a week, and you had 6.</li>
          <li>${quietWeeks} weeks with no result, including a missed check-in.</li>
          <li>Income stalled at Rp${rs.earned}M for the last 4 check-ins, while monthly clients ended.</li>` : `
          <li>Two paths still compete for your 6 free hours a week.</li>
          <li>Audits are one-off. Without new ones, income drops back.</li>`}
        </ul>
      </div>
    </div>

    <div>
      <div class="section-meta-label" style="margin-bottom:10px">${miss ? 'What do you want to do now?' : 'What next?'}</div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px">
        ${options.map(o => `
        <button class="card-clean ending-option ${choice === o.id ? 'selected' : ''}" onclick="chooseEnding('${o.id}')">
          <span class="section-meta-label" style="margin:0;color:${choice === o.id ? 'var(--open-on-ink)' : 'var(--ink-3)'}">${o.tag}</span>
          <span style="font-family:var(--font-ui);font-size:15px;font-weight:700;line-height:1.3">${o.title}</span>
          <span style="font-size:13px;line-height:1.5;opacity:0.85">${o.desc}</span>
        </button>`).join('')}
      </div>
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:16px;flex-wrap:wrap">
        <span style="font-size:12.5px;color:var(--ink-3)">${choice ? 'Your choice is saved. The map will redraw from here.' : 'Pick one. You can change it later.'}</span>
        <div style="display:flex;gap:10px">
          <button class="btn-secondary" onclick="renderScreen('08')">See the full journey</button>
          <button class="btn-primary" ${choice ? '' : 'disabled style="opacity:0.5;cursor:not-allowed"'} onclick="confirmEnding()">Start the next 30 days →</button>
        </div>
      </div>
    </div>
  </div>`;
  return renderAppShell('journey', 'Day 90 review', content);
}

function chooseEnding(id) {
  STORE.endingChoice = id;
  renderScreen('16');
}

function confirmEnding() {
  if (!STORE.endingChoice) return;
  showToast('Plan saved. The next 30 days start from what you already built.', 'View journey →', '08');
}
