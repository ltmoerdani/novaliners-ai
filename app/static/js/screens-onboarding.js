/* Onboarding screens 01 02 03 */
/* ── Screen 01 · Start (Public / Onboarding - Revenue Navigation Map) ───── */
/* Live-only notice on the Start screen: engine trouble. Maps live in the v11 sidebar (renderV11Sidebar). */
function startNotices() {
  if (IS_DEMO || ENGINE.status !== 'error') return '';
  return `<div role="alert" style="background:var(--stop-soft);border:1px solid var(--stop-border);border-radius:12px;padding:12px 16px;font-size:13px;color:var(--stop-fg);line-height:1.5"><strong>The engine is not ready.</strong> ${esc(brief(ENGINE.detail || 'Open Settings in the sidebar and check the Engine section.', 220))}</div>`;
}
function startContrastLink() {
  return IS_DEMO ? '' : `<div style="text-align:center"><a onclick="renderScreen('10')" style="font-family:var(--font-ui);font-size:12.5px;font-weight:600;color:var(--ink-3);cursor:pointer" role="button" tabindex="0" onkeydown="if(event.key==='Enter')renderScreen('10')">See how the same question gets opposite answers →</a></div>`;
}

function screen01() {
  const showScenarios = !!STORE.showStarterScenarios;

  /* v11 (2026-10-11): the Start page is home and wears the same frame as the destinations — v11 sidebar, v11 top bar
     (no active destination), content on the 680px reading measure. The old renderHomeShell sidebar is LEGACY. */
  return renderAppShell(null, 'Start', `
    <div style="width:100%;max-width:calc(680px + 2 * var(--page-x));margin:0 auto;padding:var(--page-top) var(--page-x) var(--page-bottom);display:flex;flex-direction:column;gap:24px">
      ${startNotices()}
      <!-- Eyebrow & Headline -->
      <div style="display:flex;flex-direction:column;gap:12px">
        <div class="v11-eyebrow"><span>Start</span><span class="v11-eyebrow-sep" aria-hidden="true">·</span><span>Revenue Navigation Map</span></div>

        <h1 class="serif-heading" style="margin:0">
          You don't lack tactics. You lack certainty about your next move.
        </h1>

        <p style="font-size:15.5px;color:var(--ink-2);line-height:1.6;margin:0;max-width:680px">
          Tell us where you are and where you want to be. We'll find what's really holding your income back, and give you one step for today.
        </p>
      </div>

      <!-- Primary Prompt Card (Clean AI Input Box) -->
      <div style="background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:20px 22px 18px;display:flex;flex-direction:column;gap:14px;box-shadow:0 1px 4px rgba(0,0,0,0.03);transition:border-color 0.2s" onfocuswithin="this.style.borderColor='var(--ink-muted)'">
        
        <label for="start-textarea" class="section-meta-label" style="margin:0">Where are you now, and where do you want to be?</label>
        <textarea id="start-textarea" rows="4" style="width:100%;border:none;background:transparent;outline:none;resize:vertical;font-family:var(--font-body);font-size:15px;line-height:1.6;color:var(--ink);min-height:96px" placeholder='Example: "I just quit after 10 years as a marketing manager. I want to make Rp30 million a month from consulting, but I have no clients yet. My savings cover 6 months. I was thinking about renting an office and running ads..."'>${STORE.intakePrompt || ''}</textarea>

        <!-- Quick Insertion Tags / Helper Chips -->
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding-top:4px">
          <button type="button" onclick="appendPromptTag('+ Current income')" style="display:inline-flex;align-items:center;gap:5px;font-family:var(--font-ui);font-size:12px;font-weight:500;color:var(--ink-2);background:var(--surface-tint);border:1px solid var(--border);border-radius:999px;padding:4px 12px;cursor:pointer;transition: background-color 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s, opacity 0.15s, transform 0.15s" onmouseover="this.style.background='var(--border)';this.style.color='var(--ink)'" onmouseout="this.style.background='var(--surface-tint)';this.style.color='var(--ink-2)'">
            <span>+ Current income</span>
          </button>
          <button type="button" onclick="appendPromptTag('+ Goal & timeline')" style="display:inline-flex;align-items:center;gap:5px;font-family:var(--font-ui);font-size:12px;font-weight:500;color:var(--ink-2);background:var(--surface-tint);border:1px solid var(--border);border-radius:999px;padding:4px 12px;cursor:pointer;transition: background-color 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s, opacity 0.15s, transform 0.15s" onmouseover="this.style.background='var(--border)';this.style.color='var(--ink)'" onmouseout="this.style.background='var(--surface-tint)';this.style.color='var(--ink-2)'">
            <span>+ Goal & timeline</span>
          </button>
          <button type="button" onclick="appendPromptTag('+ What I have tried')" style="display:inline-flex;align-items:center;gap:5px;font-family:var(--font-ui);font-size:12px;font-weight:500;color:var(--ink-2);background:var(--surface-tint);border:1px solid var(--border);border-radius:999px;padding:4px 12px;cursor:pointer;transition: background-color 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s, opacity 0.15s, transform 0.15s" onmouseover="this.style.background='var(--border)';this.style.color='var(--ink)'" onmouseout="this.style.background='var(--surface-tint)';this.style.color='var(--ink-2)'">
            <span>+ What I have tried</span>
          </button>
        </div>

        <!-- Footer Row inside Card: Micro Info & CTA -->
        <div style="display:flex;align-items:center;justify-content:space-between;padding-top:10px;border-top:1px solid var(--border-subtle);margin-top:2px;flex-wrap:wrap;gap:12px">
          <div style="display:flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:12px;color:var(--ink-3)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <span>5 short questions · about 6 minutes · English or Bahasa Indonesia</span>
          </div>

          <button class="btn-primary" onclick="startIntakeFlow()" style="display:inline-flex;align-items:center;gap:8px;font-family:var(--font-ui);font-size:13.5px;font-weight:600;background:var(--ink);color:var(--on-ink);border:none;border-radius:10px;padding:10px 18px;cursor:pointer;transition:background 0.15s" onmouseover="this.style.background='var(--ink-hover)'" onmouseout="this.style.background='var(--ink)'">
            <span>Start my diagnosis →</span>
          </button>
        </div>
      </div>

      <!-- Expandable Preset Scenarios -->
      <div style="display:flex;flex-direction:column;gap:10px">
        <button type="button" onclick="toggleStarterScenarios()" style="display:inline-flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:13px;font-weight:600;color:var(--ink-3);cursor:pointer;padding:4px 0;transition:color 0.15s" onmouseover="this.style.color='var(--ink)'" onmouseout="this.style.color='var(--ink-3)'">
          <span>Not sure what to write? Pick a situation like yours</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="transform:${showScenarios ? 'rotate(180deg)' : 'rotate(0)'};transition:transform 0.2s"><polyline points="6 9 12 15 18 9"/></svg>
        </button>

        ${showScenarios ? `
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(230px, 1fr));gap:10px;padding:8px 0;animation:fadeIn 0.2s ease">
          <div onclick="selectStarterScenario('I left my corporate job 2 months ago. No regular income yet, but I made Rp12.5 million from 2 projects. My goal is Rp30 million a month within 90 days.')" style="border:1px solid var(--border);border-radius:12px;padding:12px 14px;background:var(--bg-canvas);cursor:pointer;transition: background-color 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s, opacity 0.15s, transform 0.15s" onmouseover="this.style.background='var(--surface)';this.style.borderColor='var(--ink-muted)'" onmouseout="this.style.background='var(--bg-canvas)';this.style.borderColor='var(--border)'">
            <div style="font-family:var(--font-ui);font-size:12.5px;font-weight:700;color:var(--ink);margin-bottom:3px">Leaving a corporate job</div>
            <div style="font-size:12px;color:var(--ink-3);line-height:1.4">You just quit and want Rp30M a month from your skills, but have no regular clients yet.</div>
          </div>

          <div onclick="selectStarterScenario('Freelance designer for 3 years. My income goes up and down between Rp5M and Rp15M. I already work 35 hours a week. I want steady monthly clients worth Rp30M a month without burning out.')" style="border:1px solid var(--border);border-radius:12px;padding:12px 14px;background:var(--bg-canvas);cursor:pointer;transition: background-color 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s, opacity 0.15s, transform 0.15s" onmouseover="this.style.background='var(--surface)';this.style.borderColor='var(--ink-muted)'" onmouseout="this.style.background='var(--bg-canvas)';this.style.borderColor='var(--border)'">
            <div style="font-family:var(--font-ui);font-size:12.5px;font-weight:700;color:var(--ink);margin-bottom:3px">Freelancer with uneven income</div>
            <div style="font-size:12px;color:var(--ink-3);line-height:1.4">Income goes up and down and your schedule is full. You want steady monthly clients and higher prices.</div>
          </div>

          <div onclick="selectStarterScenario('My clinic booking app is built and 3 potential users have tried it, but nobody has paid yet. My goal is my first 10 paying customers.')" style="border:1px solid var(--border);border-radius:12px;padding:12px 14px;background:var(--bg-canvas);cursor:pointer;transition: background-color 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s, opacity 0.15s, transform 0.15s" onmouseover="this.style.background='var(--surface)';this.style.borderColor='var(--ink-muted)'" onmouseout="this.style.background='var(--bg-canvas)';this.style.borderColor='var(--border)'">
            <div style="font-family:var(--font-ui);font-size:12.5px;font-weight:700;color:var(--ink);margin-bottom:3px">Product without paying users</div>
            <div style="font-size:12px;color:var(--ink-3);line-height:1.4">Your product is ready but no one has bought it yet. You need your first paying customers.</div>
          </div>
        </div>
        ` : ''}
      </div>

      <!-- The signature and the three promises (README) -->
      <div style="display:flex;flex-direction:column;gap:6px;padding-top:16px;border-top:1px solid var(--border-subtle);font-family:var(--font-ui);font-size:13px;line-height:1.5;color:var(--ink-3)">
        <span style="font-weight:700;color:var(--ink-2)">GO. STOP. OR DO SOMETHING ELSE.</span>
        <span><strong style="color:var(--ink-2)">How it works:</strong> you tell us where you are → we sort facts from assumptions → you get one step, and your map updates from what happens.</span>
        <span><strong style="color:var(--ink-2)">Heads-up:</strong> we may tell you not to do something, like running ads. That's often the most valuable answer.</span>
      </div>
      ${startContrastLink()}
    </div>`);
}

/* ── Screen 02 · Diagnosis Chat (Clean Minimalist Matching Reference) ───── */
function screen02() {
  const step = STORE.chatStep !== undefined ? STORE.chatStep : (STORE.chatAnswerSubmitted ? 5 : 0);
  const isDone = step >= 5 || STORE.chatAnswerSubmitted;
  const panelOpen = !!STORE.chatEvidenceOpen;
  const evCount = isDone ? 7 : Math.min(2 + step, 6);
  const CONF_PCT = isDone ? '88%' : ['44%', '56%', '68%', '78%', '88%'][Math.min(step, 4)];
  const CONF_COLOR = (!isDone && step < 2) ? 'var(--notyet-line)' : 'var(--open-line)';

  const phases = [
    { label: 'Goal', idx: 0 },
    { label: 'Income', idx: 1 },
    { label: 'What you tried', idx: 2 },
    { label: 'Interest', idx: 3 },
    { label: 'Buying', idx: 4 }
  ];

  const PHASE_NAMES = ['Goal', 'Income', 'What you tried', 'Interest', 'Buying'];
  const curIdx = isDone ? 4 : Math.min(step, 4);
  const currentPhaseLabel = PHASE_NAMES[curIdx];
  const currentPhaseNum = curIdx + 1;
  const DIAG_EXAMPLES = [
    "A mix. Rp35 million covers my family's living costs. The rest would let me hire a junior designer so I can stop doing everything myself.",
    "A beauty clinic pays Rp12M a month (for 8 months now), a restaurant pays Rp10M a month (6 months), and a school pays Rp48M per semester (about Rp8M a month). All three are happy.",
    "7 or 8 potential clients reached out through referrals, but none of them signed. I was thinking about paying an ad agency Rp10 million.",
    "They stopped replying right after I told them my price on WhatsApp. I have never sent written examples of my past results before giving a price.",
    "They saw a website I built that was already bringing in real sales for another client. After that they trusted me and paid right away without haggling."
  ];
  const DIAG_PLACEHOLDERS = [
    'Tell us why you picked this goal...',
    'Tell us about your current monthly clients...',
    'Tell us what you have tried so far...',
    'Tell us where the conversation stopped...',
    'Tell us how your past clients decided to pay...'
  ];

  return `
  <div class="full-canvas" style="height:100%;max-height:100%;background:var(--surface);display:flex;flex-direction:column;overflow:hidden;position:relative;border-radius:12px;border:1px solid var(--border)">

    <!-- Main Content Area: Chat + In-Flow Evidence Sidebar (Shifts Chat Content to the Left when opened) -->
    <div style="flex:1;min-height:0;display:flex;position:relative;overflow:hidden;background:var(--surface);width:100%">
      
      <!-- Central Chat Column (Takes flex:1, min-height:0, shifts left when sidebar opens) -->
      <div style="flex:1;min-height:0;display:flex;flex-direction:column;align-items:center;position:relative;overflow:hidden;transition: background-color 0.2s, border-color 0.2s, color 0.2s, box-shadow 0.2s, opacity 0.2s, transform 0.2s">
        
        <!-- 1. Header: Single-Row Ultra-Clean Minimalist Header (Pinned at Top, Height: 52px) -->
        <div style="width:100%;height:52px;background:var(--surface);z-index:10;flex-shrink:0;border-bottom:1px solid var(--border-subtle);padding:0 32px;display:flex;align-items:center">
          <div style="max-width:${panelOpen ? '780px' : '860px'};margin:0 auto;width:100%;display:flex;align-items:center;justify-content:space-between;transition:max-width 0.2s ease">
            
            <!-- Left: Back to Dashboard + Engine Brand + Mini Segmented Progress Pill -->
            <div style="display:flex;align-items:center;gap:10px">
              <a onclick="renderScreen('17')" style="display:inline-flex;align-items:center;gap:5px;font-family:var(--font-ui);font-size:12.5px;font-weight:600;color:var(--ink-3);text-decoration:none;cursor:pointer;padding:4px 8px;border-radius:6px;transition: background-color 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s, opacity 0.15s, transform 0.15s" onmouseover="this.style.color='var(--ink)';this.style.background='var(--surface-tint)'" onmouseout="this.style.color='var(--ink-3)';this.style.background='transparent'" title="Back to Dashboard">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>
                <span>Diagnosis</span>
              </a>
              <span style="color:var(--border);font-size:13px">/</span>

              <!-- Sleek Mini Progress Pill (5 micro-bars) -->
              <div style="display:inline-flex;align-items:center;gap:7px;padding:3px 9px 3px 8px;border-radius:999px;background:var(--surface-3);border:1px solid var(--border);margin-left:4px" title="Progress: step ${currentPhaseNum} of 5 (${currentPhaseLabel})">
                <div style="display:flex;align-items:center;gap:3px">
                  ${phases.map((tab, idx) => {
                    let fill = 'var(--border)';
                    if (isDone || idx < step) {
                      fill = 'var(--open-line)';
                    } else if (idx === step) {
                      fill = 'var(--notyet-line)';
                    }
                    return `<div style="width:8px;height:3px;border-radius:2px;background:${fill};transition:background 0.25s"></div>`;
                  }).join('')}
                </div>
                <span style="font-family:var(--font-ui);font-size:11.5px;font-weight:600;color:var(--ink-2)">
                  ${isDone ? '5/5 · Done' : `Step ${currentPhaseNum}/5 · ${currentPhaseLabel}`}
                </span>
              </div>
            </div>

            <!-- Right Controls: [ ⟲ ] [ ◫ Evidence summary · X ] [ ● active session ] -->
            <div style="display:flex;align-items:center;gap:8px">
              <!-- Reset Button -->
              <button onclick="resetDiagChat()" style="display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;padding:0;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--ink-2);cursor:pointer;box-shadow:0 1px 2px rgba(0,0,0,0.02);transition: background-color 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s, opacity 0.15s, transform 0.15s" onmouseover="this.style.background='var(--surface-tint)';this.style.color='var(--ink)'" onmouseout="this.style.background='var(--surface)';this.style.color='var(--ink-2)'" title="Start the questions over">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                  <path d="M3 3v5h5"/>
                </svg>
              </button>

              <!-- Evidence Summary Button: ONLY APPEARS WHEN THE SIDEBAR IS CLOSED (!panelOpen) -->
              ${!panelOpen ? `
              <button class="btn-secondary btn-sm" onclick="toggleEvidencePanel()" style="display:inline-flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:12px;font-weight:500;color:var(--ink-2b);background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:0 10px;height:28px;cursor:pointer;white-space:nowrap;transition:background 0.15s" onmouseover="this.style.background='var(--surface-tint)'" onmouseout="this.style.background='var(--surface)'" title="Open summary">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
                <span>What we know · ${evCount}</span>
              </button>
              ` : ''}
            </div>

          </div>
        </div>

        <!-- 2. Scrollable Messages Area: THE CONTENT INSIDE THE CHAT IS WHAT SCROLLS! -->
        <div id="chat-messages-container" style="flex:1;min-height:0;width:100%;display:flex;justify-content:center;overflow-y:auto;scrollbar-width:thin;scrollbar-color:var(--border-strong) transparent;padding:28px 32px 24px">
          <div style="width:100%;max-width:${panelOpen ? '780px' : '860px'};display:flex;flex-direction:column;gap:24px;transition:max-width 0.2s ease">
            
            <!-- Bot Question 1 · Phase 1 (Target) -->
            <div style="display:flex;flex-direction:column;gap:6px">
              <div style="display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--ink-3)">
                <span>Novaliners</span>
                <span>· 19:30</span>
              </div>
              <div style="font-size:15px;line-height:1.65;color:var(--ink)">
                From what you shared: you make Rp30 million a month and want to reach Rp60 million within 90 days.
                <br><br>
                <strong>What is the Rp60 million for? Covering your living costs, or growing the business?</strong>
              </div>
            </div>

            ${step >= 1 ? `
            <!-- User Answer 1 · Phase 1 (Target) -->
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
              <div style="display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--ink-3)">
                <span style="font-weight:600">You</span>
                <span>· 19:30</span>
              </div>
              <div style="background:var(--surface-tint);border-radius:14px;padding:14px 18px;font-size:14px;line-height:1.6;color:var(--ink);max-width:85%">
                ${STORE.chatUserAnswer1 || "A mix. Rp35 million covers my family's living costs. The rest would let me hire a junior designer so I can stop doing everything myself."}
              </div>
            </div>

            <!-- Bot Question 2 · Phase 2 (Income) -->
            <div style="display:flex;flex-direction:column;gap:6px">
              <div style="display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--ink-3)">
                <span>Novaliners</span>
                <span>· 19:31</span>
              </div>
              <div style="font-size:15px;line-height:1.65;color:var(--ink)">
                One thing stands out: you already work 34.5 hours a week on your own, so you are close to your limit. Taking on more clients at the same price could burn you out.
                <br><br>
                <strong>Can you tell us about the 3 clients who pay you every month?</strong>
              </div>
            </div>
            ` : ''}

            ${step >= 2 ? `
            <!-- User Answer 2 · Phase 2 (Income) -->
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
              <div style="display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--ink-3)">
                <span style="font-weight:600">You</span>
                <span>· 19:31</span>
              </div>
              <div style="background:var(--surface-tint);border-radius:14px;padding:14px 18px;font-size:14px;line-height:1.6;color:var(--ink);max-width:85%">
                ${STORE.chatUserAnswer2 || "A beauty clinic pays Rp12M a month (for 8 months now), a restaurant pays Rp10M a month (6 months), and a school pays Rp48M per semester (about Rp8M a month). All three are happy."}
              </div>
            </div>

            <!-- Bot Question 3 · Phase 3 (Activity) -->
            <div style="display:flex;flex-direction:column;gap:6px">
              <div style="display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--ink-3)">
                <span>Novaliners</span>
                <span>· 19:32</span>
              </div>
              <div style="font-size:15px;line-height:1.65;color:var(--ink)">
                All your clients stay with you and are happy with your work.
                <br><br>
                <strong>What have you tried in the last 90 days to earn more or find new clients?</strong>
              </div>
            </div>
            ` : ''}

            ${step >= 3 ? `
            <!-- User Answer 3 · Phase 3 (Activity) -->
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
              <div style="display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--ink-3)">
                <span style="font-weight:600">You</span>
                <span>· 19:32</span>
              </div>
              <div style="background:var(--surface-tint);border-radius:14px;padding:14px 18px;font-size:14px;line-height:1.6;color:var(--ink);max-width:85%">
                ${STORE.chatUserAnswer3 || "7 or 8 potential clients reached out through referrals, but none of them signed. I was thinking about paying an ad agency Rp10 million."}
              </div>
            </div>

            <!-- Bot Question 4 · Phase 4 (Demand) -->
            <div style="display:flex;flex-direction:column;gap:6px">
              <div style="display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--ink-3)">
                <span>Novaliners</span>
                <span>· 19:33</span>
              </div>
              <div style="font-size:15px;line-height:1.65;color:var(--ink)">
                8 people asking about your work without any ads is a strong sign that people want what you offer.
                <br><br>
                <strong>With those 7 or 8 people, where did the conversation stop? Did you show them examples of your results before telling them your price?</strong>
              </div>
            </div>
            ` : ''}

            ${step >= 4 ? `
            <!-- User Answer 4 · Phase 4 (Demand) -->
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
              <div style="display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--ink-3)">
                <span style="font-weight:600">You</span>
                <span>· 19:33</span>
              </div>
              <div style="background:var(--surface-tint);border-radius:14px;padding:14px 18px;font-size:14px;line-height:1.6;color:var(--ink);max-width:85%">
                ${STORE.chatUserAnswer4 || "They stopped replying right after I told them my price on WhatsApp. I have never sent written examples of my past results before giving a price."}
              </div>
            </div>

            <!-- Bot Question 5 · Phase 5 (Conversion) -->
            <div style="display:flex;flex-direction:column;gap:6px">
              <div style="display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--ink-3)">
                <span>Novaliners</span>
                <span>· 19:34</span>
              </div>
              <div style="font-size:15px;line-height:1.65;color:var(--ink)">
                Last question, and an important one.
                <br><br>
                <strong>When your 3 current clients agreed to hire you, did they pay right away, or only after seeing real examples of your work?</strong>
              </div>
            </div>
            ` : ''}

            ${isDone ? `
            <!-- User Answer 5 · Phase 5 (Conversion) -->
            <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
              <div style="display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--ink-3)">
                <span style="font-weight:600">You</span>
                <span>· 19:34</span>
              </div>
              <div style="background:var(--surface-tint);border-radius:14px;padding:14px 18px;font-size:14px;line-height:1.6;color:var(--ink);max-width:85%">
                ${STORE.chatUserAnswer5 || "They saw a website I built that was already bringing in real sales for another client. After that they trusted me and paid right away without haggling."}
              </div>
            </div>

            <!-- Convergence Verdict Card -->
            <div style="background:var(--ink);color:var(--on-ink);padding:26px 30px;border-radius:16px;display:flex;flex-direction:column;gap:14px;box-shadow:0 8px 24px rgba(0,0,0,0.12);margin-top:8px">
              <div style="display:flex;align-items:center;justify-content:space-between">
                <span style="font-family:var(--font-ui);font-size:12px;font-weight:600;color:var(--open-on-ink-2)">Diagnosis done · 88% confident</span>
                <span style="font-size:12px;color:var(--ink-muted)">All your answers point the same way</span>
              </div>
              <div>
                <h2 style="font-family:var(--font-ui);font-size:20px;font-weight:700;margin:0 0 6px">The main problem: new clients can't see proof of your results</h2>
                <p style="font-size:14px;color:var(--border-strong);line-height:1.6;margin:0">
                  Your skills already sell: 3 clients pay you every month. The problem isn't the quality of your work. It's that you don't have a ready-made offer that new clients can simply say yes to.
                </p>
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center;padding-top:12px;border-top:1px solid var(--ink-hover);margin-top:4px">
                <a onclick="resetDiagChat()" style="font-size:12.5px;color:var(--ink-muted);cursor:pointer;text-decoration:none;display:flex;align-items:center;gap:6px">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/></svg>
                  Start the questions over
                </a>
                <button class="btn-primary" style="background:var(--surface);color:var(--ink);font-weight:700;height:42px;padding:0 22px;font-size:14px" onclick="renderScreen('03')">
                  See my results &amp; map →
                </button>
              </div>
            </div>
            ` : ''}

          </div>
        </div>

        <!-- 3. Fixed Bottom Input Bar: STAY AT THE BOTTOM! (flex-shrink: 0) -->
        ${!isDone ? `
        <div style="width:100%;background:var(--surface);border-top:1px solid var(--border-subtle);flex-shrink:0;padding:10px 32px 18px;display:flex;justify-content:center;z-index:10">
          <div style="width:100%;max-width:${panelOpen ? '780px' : '860px'};display:flex;flex-direction:column;gap:8px;transition:max-width 0.2s ease">
            
            <!-- EXAMPLE ANSWER Chip (Line Style) -->
            <button onclick="fillExampleAnswer()" style="width:100%;text-align:left;padding:10px 14px;border:1px dashed var(--border-strong);border-radius:10px;background:var(--surface);display:flex;flex-direction:column;gap:3px;cursor:pointer;transition: background-color 0.15s, border-color 0.15s, color 0.15s, box-shadow 0.15s, opacity 0.15s, transform 0.15s" onmouseover="this.style.borderColor='var(--ink-3)';this.style.background='var(--bg-canvas)'" onmouseout="this.style.borderColor='var(--border-strong)';this.style.background='var(--surface)'">
              <span style="font-family:var(--font-ui);font-size:11px;font-weight:600;color:var(--ink-muted)">Use example answer ↵</span>
              <span style="font-size:13px;line-height:1.45;color:var(--ink-2b)">${DIAG_EXAMPLES[Math.min(step, 4)]}</span>
            </button>

            <!-- Textarea Input Box -->
            <div style="background:var(--surface);border:1px solid var(--border-strong);border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,0.03);display:flex;flex-direction:column;padding:2px">
              <textarea id="diag-chat-input" rows="2" placeholder="${DIAG_PLACEHOLDERS[Math.min(step, 4)]}" style="border:none;outline:none;resize:none;background:transparent;color:var(--ink);font-family:var(--font-ui);font-size:14px;line-height:1.5;padding:10px 14px 6px;border-radius:10px" onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendDiagChat();}"></textarea>
              <div style="display:flex;align-items:center;justify-content:space-between;padding:2px 12px 8px 14px">
                <span style="font-size:11.5px;color:var(--ink-muted);font-family:var(--font-ui);display:flex;align-items:center;gap:6px">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  Use real numbers where you can
                </span>
                <button class="btn-primary" style="width:32px;height:32px;border-radius:50%;padding:0;display:flex;align-items:center;justify-content:center;cursor:pointer" onclick="sendDiagChat()" title="Send answer">↑</button>
              </div>
            </div>

          </div>
        </div>
        ` : ''}

      </div>

      <!-- In-Flow Right Sidebar (Shifts Chat Content to Left, Does NOT Cover Chat) -->
      ${panelOpen ? `
      <aside style="width:360px;min-width:360px;flex-shrink:0;height:100%;background:var(--surface);border-left:1px solid var(--border);box-shadow:-4px 0 16px rgba(0,0,0,0.03);padding:20px 22px;overflow-y:auto;display:flex;flex-direction:column;gap:18px">
        <!-- Top bar of sidebar (Matching User's Screenshot Exactly) -->
        <div style="display:flex;align-items:flex-start;justify-content:space-between">
          <div style="display:flex;flex-direction:column;gap:5px">
            <span style="font-family:var(--font-ui);font-weight:700;font-size:13px;color:var(--ink)">What we know so far</span>
            <div style="display:inline-flex;align-items:center;background:var(--surface-tint);border:1px solid var(--border);border-radius:999px;padding:2px 10px;font-size:11.5px;font-weight:600;color:var(--ink-2);width:fit-content">
              Timeline: 90 days
            </div>
          </div>
          <!-- Close/Collapse Button (Line Style Icon per screenshot) -->
          <button onclick="toggleEvidencePanel()" style="display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:6px;border:1px solid var(--border);background:var(--surface);cursor:pointer;color:var(--ink-2);box-shadow:0 1px 2px rgba(0,0,0,0.02);transition:background 0.15s" onmouseover="this.style.background='var(--surface-tint)'" onmouseout="this.style.background='var(--surface)'" title="Close summary">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="15" y1="3" x2="15" y2="21"/></svg>
          </button>
        </div>

        <p style="margin:0;font-size:12px;line-height:1.5;color:var(--ink-3)">From your answers: what you want, what happened, and what holds today. The questions follow what is still unclear, not these groups.</p>

        <!-- Stats Meter (Matching User's Screenshot Exactly) -->
        <div style="display:flex;flex-direction:column;gap:6px">
          <div style="font-size:12px;font-family:var(--font-ui);display:flex;align-items:center;gap:6px">
            <span style="font-weight:600;color:var(--ink)">${evCount} facts collected</span>
            <span style="color:var(--border-strong)">·</span>
            <span style="color:var(--stop-fg);font-weight:600">${Math.max(0, 8 - evCount)} more needed</span>
          </div>
          <div style="display:flex;align-items:center;justify-content:space-between;font-size:11.5px;font-family:var(--font-ui);color:var(--ink-3)">
            <span>Confidence</span>
            <span style="font-weight:700;color:var(--ink)">${CONF_PCT} · ${isDone || step >= 3 ? 'High' : 'Medium'}</span>
          </div>
          <div style="height:3px;background:var(--border);border-radius:2px;overflow:hidden">
            <div style="width:${CONF_PCT};height:100%;background:${CONF_COLOR};border-radius:2px;transition:width 0.3s ease"></div>
          </div>
        </div>


        <!-- Evidence cards grouped by claim ROLE (same grouping as the live panel in screens-live-chat.js).
             Demo data only: this onboarding screen shows canned answers so the grouping is visible before
             a real session exists. Progressive disclosure still follows the demo conversation steps. -->
        <div style="display:flex;flex-direction:column;gap:16px">
          <!-- Role: goal -->
          <div>
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
              <div style="display:flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:12px;font-weight:700;color:var(--ink)">
                <span style="width:6px;height:6px;border-radius:50%;background:${ROLE_UI.goal.color};display:inline-block"></span>
                <span>Goal</span>
              </div>
              <span style="font-size:11.5px;color:var(--ink-3)">1</span>
            </div>
            <div style="font-size:11px;color:var(--ink-3);line-height:1.4;margin-bottom:8px">${esc(ROLE_UI.goal.desc)}</div>
            <div class="card-clean" style="padding:10px 12px">
              <div style="font-size:12.5px;font-weight:600;color:var(--ink)">Goal: Rp60M a month in 90 days (Rp30M more than now)</div>
              <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
                <span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:500;color:var(--ink-3)">
                  <span style="width:5px;height:5px;border-radius:50%;background:var(--ink-3);display:inline-block"></span> Your goal
                </span>
                <span style="font-size:10.5px;color:var(--ink-muted)">↗ 19:31</span>
              </div>
            </div>
          </div>

          <!-- Role: desire (Shown when step >= 1) -->
          ${step >= 1 ? `
          <div>
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
              <div style="display:flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:12px;font-weight:700;color:var(--ink)">
                <span style="width:6px;height:6px;border-radius:50%;background:${ROLE_UI.desire.color};display:inline-block"></span>
                <span>Wants</span>
              </div>
              <span style="font-size:11.5px;color:var(--ink-3)">1</span>
            </div>
            <div style="font-size:11px;color:var(--ink-3);line-height:1.4;margin-bottom:8px">${esc(ROLE_UI.desire.desc)}</div>
            <div class="card-clean" style="padding:10px 12px">
              <div style="font-size:12.5px;font-weight:600;color:var(--ink)">The rest would let me hire a junior designer, so I stop doing everything myself</div>
              <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
                <span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:500;color:var(--violet)">
                  <span style="width:5px;height:5px;border-radius:50%;background:var(--violet);display:inline-block"></span> Why it matters
                </span>
                <span style="font-size:10.5px;color:var(--ink-muted)">↗ 19:31</span>
              </div>
            </div>
          </div>
          ` : ''}

          <!-- Role: event (Shown when step >= 2) -->
          ${step >= 2 ? `
          <div>
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
              <div style="display:flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:12px;font-weight:700;color:var(--ink)">
                <span style="width:6px;height:6px;border-radius:50%;background:${ROLE_UI.event.color};display:inline-block"></span>
                <span>Events</span>
              </div>
              <span style="font-size:11.5px;color:var(--ink-3)">1</span>
            </div>
            <div style="font-size:11px;color:var(--ink-3);line-height:1.4;margin-bottom:8px">${esc(ROLE_UI.event.desc)}</div>
            <div class="card-clean" style="padding:10px 12px">
              <div style="font-size:12.5px;font-weight:600;color:var(--ink)">7 or 8 potential clients reached out through referrals</div>
              <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
                <span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:500;color:var(--notyet-line)">
                  <span style="width:5px;height:5px;border-radius:50%;background:var(--notyet-line);display:inline-block"></span> Something that happened
                </span>
                <span style="font-size:10.5px;color:var(--ink-muted)">↗ 19:32</span>
              </div>
            </div>
          </div>
          ` : ''}

          <!-- Role: claim (facts about today) -->
          <div>
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
              <div style="display:flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:12px;font-weight:700;color:var(--ink)">
                <span style="width:6px;height:6px;border-radius:50%;background:${ROLE_UI.claim.color};display:inline-block"></span>
                <span>Facts</span>
              </div>
              <span style="font-size:11.5px;color:var(--ink-3)">${step >= 2 ? 3 : 2} facts</span>
            </div>
            <div style="font-size:11px;color:var(--ink-3);line-height:1.4;margin-bottom:8px">${esc(ROLE_UI.claim.desc)}</div>
            <div class="card-clean" style="padding:10px 12px;margin-bottom:8px">
              <div style="font-size:12.5px;font-weight:600;color:var(--ink)">Now earning Rp30M a month from 3 monthly clients</div>
              <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
                <span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:500;color:var(--open-line)">
                  <span style="width:5px;height:5px;border-radius:50%;background:var(--open-line);display:inline-block"></span> Real payment
                </span>
                <span style="font-size:10.5px;color:var(--ink-muted)">↗ 19:31</span>
              </div>
            </div>
            <div class="card-clean" style="padding:10px 12px;${step >= 2 ? 'margin-bottom:8px;' : ''}">
              <div style="font-size:12.5px;font-weight:600;color:var(--ink)">3 monthly clients: Rp12M + Rp10M + Rp8M a month</div>
              <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
                <span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:500;color:var(--open-line)">
                  <span style="width:5px;height:5px;border-radius:50%;background:var(--open-line);display:inline-block"></span> Real payment
                </span>
                <span style="font-size:10.5px;color:var(--ink-muted)">↗ 19:31</span>
              </div>
            </div>
            ${step >= 2 ? `
            <div class="card-clean" style="padding:10px 12px">
              <div style="font-size:12.5px;font-weight:600;color:var(--ink)">Already working 34.5 hours a week (at your limit)</div>
              <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
                <span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:500;color:var(--notyet-line)">
                  <span style="width:5px;height:5px;border-radius:50%;background:var(--notyet-line);display:inline-block"></span> Your words
                </span>
                <span style="font-size:10.5px;color:var(--ink-muted)">↗ 19:31</span>
              </div>
            </div>` : ''}
          </div>

          ${step >= 4 ? `
          <!-- Role: claim, buying behaviour -->
          <div>
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
              <div style="display:flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:12px;font-weight:700;color:var(--ink)">
                <span style="width:6px;height:6px;border-radius:50%;background:${ROLE_UI.claim.color};display:inline-block"></span>
                <span>Facts</span>
              </div>
              <span style="font-size:11.5px;color:var(--ink-3)">1 fact</span>
            </div>
            <div style="font-size:11px;color:var(--ink-3);line-height:1.4;margin-bottom:8px">How people actually end up paying you.</div>
            <div class="card-clean" style="padding:10px 12px">
              <div style="font-size:12.5px;font-weight:600;color:var(--ink)">Past clients paid after seeing real results</div>
              <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
                <span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:500;color:var(--violet)">
                  <span style="width:5px;height:5px;border-radius:50%;background:var(--violet);display:inline-block"></span> How people buy
                </span>
                <span style="font-size:10.5px;color:var(--ink-muted)">↗ 19:34</span>
              </div>
            </div>
          </div>` : ''}

          ${step >= 3 ? `
          <!-- Gaps: what the user said they do not know yet (own section, never mixed with facts) -->
          <div style="border-top:1px dashed var(--border-strong);padding-top:14px">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
              <div style="display:flex;align-items:center;gap:6px;font-family:var(--font-ui);font-size:12px;font-weight:700;color:var(--ink-3)">
                <span style="width:6px;height:6px;border-radius:50%;background:${GAP_UI.color};display:inline-block"></span>
                <span>Still to learn</span>
              </div>
              <span style="font-size:11.5px;color:var(--ink-3)">1</span>
            </div>
            <div style="font-size:11px;color:var(--ink-3);line-height:1.4;margin-bottom:8px">${esc(GAP_UI.desc)}</div>
            <div class="card-clean" style="padding:10px 12px;border-style:dashed">
              <div style="font-size:12.5px;font-weight:600;color:var(--ink-2)">Why those referral talks stopped is not known yet</div>
              <div style="display:flex;align-items:center;justify-content:space-between;margin-top:6px">
                <span style="display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:500;color:var(--ink-muted)">
                  <span style="width:5px;height:5px;border-radius:50%;background:var(--ink-muted);display:inline-block"></span> Not known yet
                </span>
                <span style="font-size:10.5px;color:var(--ink-muted)">↗ 19:33</span>
              </div>
            </div>
          </div>` : ''}
        </div>
      </aside>
      ` : ''}

    </div>
  </div>`;
}

function toggleEvidencePanel() {
  STORE.chatEvidenceOpen = !STORE.chatEvidenceOpen;
  renderScreen('02');
}

function toggleGuide5Phase() {
  STORE.guide5PhaseOpen = STORE.guide5PhaseOpen === undefined ? false : !STORE.guide5PhaseOpen;
  renderScreen('02');
}

const DIAG_DEFAULT_ANSWERS = [
  "A mix. Rp35 million covers my family's living costs. The rest would let me hire a junior designer so I can stop doing everything myself.",
  "A beauty clinic pays Rp12M a month (for 8 months now), a restaurant pays Rp10M a month (6 months), and a school pays Rp48M per semester (about Rp8M a month). All three are happy.",
  "7 or 8 potential clients reached out through referrals, but none of them signed. I was thinking about paying an ad agency Rp10 million.",
  "They stopped replying right after I told them my price on WhatsApp. I have never sent written examples of my past results before giving a price.",
  "They saw a website I built that was already bringing in real sales for another client. After that they trusted me and paid right away without haggling."
];

function fillExampleAnswer() {
  const input = document.getElementById('diag-chat-input');
  if (input) {
    const step = STORE.chatStep !== undefined ? STORE.chatStep : 0;
    input.value = DIAG_DEFAULT_ANSWERS[Math.min(step, 4)];
    input.focus();
  }
}

function sendDiagChat() {
  const input = document.getElementById('diag-chat-input');
  const step = STORE.chatStep !== undefined ? STORE.chatStep : 0;
  const s = Math.min(step, 4);
  const txt = (input && input.value.trim()) ? input.value.trim() : DIAG_DEFAULT_ANSWERS[s];
  STORE['chatUserAnswer' + (s + 1)] = txt;
  STORE.chatUserAnswer = txt;
  STORE.chatStep = s + 1;
  if (s >= 4) STORE.chatAnswerSubmitted = true;
  renderScreen('02');
  setTimeout(() => {
    const el = document.getElementById('chat-messages-container');
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    if (s < 4) {
      const newInput = document.getElementById('diag-chat-input');
      if (newInput) {
        newInput.value = '';
        newInput.focus();
      }
    }
  }, 40);
}

function resetDiagChat() {
  STORE.chatStep = 0;
  STORE.chatAnswerSubmitted = false;
  STORE.chatUserAnswer1 = '';
  STORE.chatUserAnswer2 = '';
  STORE.chatUserAnswer3 = '';
  STORE.chatUserAnswer4 = '';
  STORE.chatUserAnswer5 = '';
  STORE.chatUserAnswer = '';
  renderScreen('02');
  setTimeout(() => {
    const el = document.getElementById('chat-messages-container');
    if (el) el.scrollTo({ top: 0, behavior: 'smooth' });
    const input = document.getElementById('diag-chat-input');
    if (input) {
      input.value = '';
      input.focus();
    }
  }, 40);
}


function screen03() {
  return `<div class="full-canvas" style="min-height:100vh;background:var(--surface)">
    ${renderOnboardingTopBar(2, "Review answers", "renderScreen('02')")}
    <div style="max-width:1120px;margin:0 auto;padding:48px 32px 96px;display:flex;flex-direction:column;gap:32px">
      <div>
        <div style="display:flex;align-items:center;gap:8px;font-family:var(--font-ui);font-size:13px;margin-bottom:8px">
          <span class="section-meta-label">Your diagnosis</span>
          <span>·</span>
          <span style="font-weight:700">High confidence</span>
          <span>·</span>
          <a onclick="openDrawer()" style="font-weight:600">Why?</a>
        </div>
        <h1 class="serif-heading" style="font-size:42px">Your expertise isn't the problem. It just isn't packaged as an offer yet.</h1>
        <div style="display:flex;align-items:center;gap:12px;margin-top:14px">
          <span class="status-pill" style="background:var(--ink);color:var(--on-ink)">GO SMALL</span>
          <span style="font-size:15px;color:var(--ink-2);font-weight:500">Move, but don't spend money yet.</span>
        </div>
      </div>

      <!-- 3 Grid Cards -->
      <div style="display:grid;grid-template-columns:repeat(3, 1fr);gap:20px">
        <div class="card-clean" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div class="section-meta-label">What's blocking you</div>
            <h2 style="font-family:var(--font-ui);font-size:18px;font-weight:700;margin-bottom:6px">You have no written offer to send.</h2>
            <p style="font-size:13.5px;color:var(--ink-2);line-height:1.55">Two people asked to hear from you when you start, but there's nothing specific for them to say yes to.</p>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:14px">
            <span class="evidence-chip">Based on: 2 paid projects</span>
            <span class="evidence-chip">2 contacts asked</span>
          </div>
        </div>

        <div class="card-danger" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div class="section-meta-label" style="color:var(--stop-fg)">What not to do yet</div>
            <h2 style="font-family:var(--font-ui);font-size:18px;font-weight:700;color:var(--stop-fg);margin-bottom:6px">Don't rent the office.</h2>
            <p style="font-size:13.5px;color:var(--ink-2);line-height:1.55">No client has asked where you work. Also on hold: LinkedIn ads and registering a company.</p>
          </div>
          <span class="status-pill stop" style="align-self:flex-start;margin-top:14px">Keeps Rp20M in your pocket</span>
        </div>

        <div class="card-dark" style="display:flex;flex-direction:column;justify-content:space-between">
          <div>
            <div class="section-meta-label" style="color:var(--border-strong)">Your next move · 25 min</div>
            <h2 style="font-family:var(--font-ui);font-size:18px;font-weight:700;margin-bottom:6px">Write a one-page offer: problem, result, price.</h2>
            <p style="font-size:13.5px;color:var(--border);line-height:1.55">It worked if 1 of the 2 contacts replies with a question.</p>
          </div>
          <button class="btn-primary" style="background:var(--surface);color:var(--ink);width:100%;margin-top:14px" onclick="renderScreen('04')">
            Start this path →
          </button>
        </div>
      </div>

      <!-- Tip Callout -->
      <div class="tip-bubble pointer-left" style="max-width:580px">
        <div style="font-family:var(--font-ui);font-size:12px;font-weight:600;color:var(--on-dark-2);margin-bottom:2px">Tip · shown once</div>
        <div style="font-family:var(--font-ui);font-size:14px;font-weight:700;margin-bottom:4px">Why am I being told no?</div>
        <div style="font-size:12.5px;color:var(--on-dark-3);line-height:1.5;margin-bottom:10px">Stopping a costly move early is often worth more than a new tactic. Every block has a reason and a way to reopen it, and the final call is always yours.</div>
        <button class="btn-secondary btn-sm" style="background:var(--surface);border:none;color:var(--ink)" onclick="this.closest('.tip-bubble').style.display='none'">Got it</button>
      </div>

      <!-- DEMO (prototype v9, Dimas): "5 paths" is the demo's illustrative story, pinned pixel for pixel by the parity suite.
           It is not the contract: live mode reads possible_paths (0..N) and draws at most five (internal-docs §24). -->
      <div class="card-clean" style="padding:0;overflow:hidden">
        <button style="width:100%;padding:16px 20px;display:flex;align-items:center;justify-content:space-between" onclick="toggleCollapse('collapse-paths')">
          <div style="text-align:left">
            <div style="font-family:var(--font-ui);font-size:15px;font-weight:700">See all 5 paths to Rp30M a month</div>
            <div style="font-size:12.5px;color:var(--ink-2)">1 open · 1 to test · 2 locked for now · 1 stopped</div>
          </div>
          <span>▾</span>
        </button>
        <div id="collapse-paths" style="display:none;padding:16px 20px;border-top:1px solid var(--border)">
          <div style="display:flex;flex-direction:column;gap:10px">
            <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:var(--open-soft);border-radius:8px">
              <div style="display:flex;align-items:center;gap:10px">
                ${getPathGlyph('OPEN')}
                <span style="font-family:var(--font-ui);font-weight:700;font-size:14px">Advising people you know</span>
              </div>
              <span class="status-pill open">OPEN</span>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:var(--surface-2);border-radius:8px">
              <div style="display:flex;align-items:center;gap:10px">
                ${getPathGlyph('TEST_FIRST')}
                <span style="font-family:var(--font-ui);font-weight:600;font-size:14px">Freelancing for agencies</span>
              </div>
              <span class="status-pill test_first">TEST FIRST</span>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:var(--surface-2);border-radius:8px">
              <div style="display:flex;align-items:center;gap:10px">
                ${getPathGlyph('NOT_YET')}
                <span style="font-family:var(--font-ui);font-weight:600;font-size:14px">Fixed-price brand audit</span>
              </div>
              <span class="status-pill not_yet">NOT YET</span>
            </div>
            <div style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;background:var(--surface-2);border-radius:8px">
              <div style="display:flex;align-items:center;gap:10px">
                ${getPathGlyph('STOP')}
                <span style="font-family:var(--font-ui);font-weight:600;font-size:14px">Paid LinkedIn ads</span>
              </div>
              <span class="status-pill stop">STOP</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>`;
}

function toggleCollapse(id) {
  const el = document.getElementById(id);
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
}
