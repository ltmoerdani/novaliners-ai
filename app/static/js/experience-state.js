/* Experience read model client (V4 master prompt section 4; audit D-04/D-05/D-08).
   One version-bound read of the server's composed reality: STATE, MAPS, MOVES, JOURNEY and TALK
   compare the SAME projection_revision, so a screen that is behind can say so instead of showing a
   mixed snapshot. It never invents state: on failure the last good revision is kept, the failure is
   reported, and business mutations stay with the canonical endpoints. */
LIVE.experience = null;
LIVE.experienceError = null;
LIVE.experiencePending = false;
LIVE.pendingRouteOps = LIVE.pendingRouteOps || {};

/* D-10: stable operation key for a user action. The caller keeps the key for retries of the SAME
   action so the server replays the accepted event instead of appending a second one. */
function newOperationId(prefix) {
  const a = new Uint8Array(8);
  (window.crypto || {}).getRandomValues ? crypto.getRandomValues(a) : a.forEach((_, i) => { a[i] = Math.floor(Math.random() * 256); });
  return (prefix || 'op') + '-' + Array.from(a).map(b => b.toString(16).padStart(2, '0')).join('');
}

function liveExperienceRevision() {
  return (LIVE.experience && LIVE.experience.revision) || null;
}
/* The checkpoint the version-bound read currently reflects. The projection revision is the primary
   witness (it is stamped by the same read); the checkpoint summary is a separate copy; state.reality
   is the fallback for a state-only snapshot. Never derived from a diagnosis or a local guess. */
function liveCheckpointId() {
  const rev = (LIVE.experience && LIVE.experience.revision) || null;
  if (rev && rev.checkpoint_id) return String(rev.checkpoint_id);
  const cp = (LIVE.experience && LIVE.experience.checkpoint) || null;
  if (cp && cp.checkpoint_id) return String(cp.checkpoint_id);
  const reality = (LIVE.state && LIVE.state.reality) || null;
  return (reality && reality.checkpoint_id) ? String(reality.checkpoint_id) : '';
}
function liveExperienceStateWord() {
  if (LIVE.experienceError) return 'stale';
  if (LIVE.experiencePending) return 'refreshing';
  return LIVE.experience ? 'current' : 'none';
}
/* Fetch the composed read model. A late response for a map the user already left is dropped, so a
   slow request can never overwrite the open map's reality (the same guard the rest of LIVE uses). */
async function liveLoadExperience() {
  const sid = LIVE.sid;
  if (IS_DEMO || !sid) { LIVE.experience = null; LIVE.experienceError = null; return null; }
  LIVE.experiencePending = true;
  try {
    const exp = await API.experience(sid);
    if (LIVE.sid !== sid) return null;
    LIVE.experience = exp;
    LIVE.experienceError = null;
    return exp;
  } catch (e) {
    if (LIVE.sid !== sid) return null;
    LIVE.experienceError = (e && e.message) ? e.message : String(e);
    return null;
  } finally {
    if (LIVE.sid === sid) LIVE.experiencePending = false;
  }
}
/* Refresh after an accepted mutation. If projection_revision actually moved, the derived route and
   readiness caches are recomposed from the same server truth and the open surface redraws. Cheap and
   deterministic: no LLM call, no reassessment, no guessed reality. */
async function liveRefreshExperience() {
  const before = liveExperienceRevision();
  const exp = await liveLoadExperience();
  if (!exp) return null;
  const after = liveExperienceRevision();
  if (before && after && before.projection_revision !== after.projection_revision) {
    try { await liveLoadRoutes(); } catch (e) { /* derived cache only */ }
    try { await liveLoadReadiness(); } catch (e) { /* derived cache only */ }
    if (typeof renderScreenKeepingUi === 'function' && ['state', 'maps', 'moves', 'journey'].includes(STORE.currentScreen)) {
      renderScreenKeepingUi(STORE.currentScreen);
    }
  }
  return exp;
}
/* P0-01: ONE orchestrated refresh boundary after an accepted mutation. It reads Experience, State,
   Evidence, Navigation, Readiness, Routes and Moves for the SAME session, drops a late response for a
   map the user already left, and refuses to commit a mixed-version snapshot.

   ATOMICITY: every response is fetched into a CANDIDATE, never straight into the LIVE globals. LIVE is
   written only after the candidate passes validation (session identity, required payloads, one
   consistent projection_revision across all surfaces, and - when the caller named one - the EXPECTED
   CHECKPOINT read out of the candidate itself). On a mismatch the WHOLE read is retried once and the
   reference revision is recomputed from the NEW response. If it still fails, the complete previous
   snapshot is preserved, a stale state is exposed, and NO partially refreshed data is rendered.

   STRICTNESS: opts.strictSources (a reassessment commit) additionally requires every revision-carrying
   source to have actually been READ, because apply() only writes non-null values and a failed source
   would otherwise keep a PRE-commit value inside a snapshot claiming one revision. Absent, the
   tolerant behaviour above is unchanged. */
LIVE.refreshToken = LIVE.refreshToken || 0;
LIVE.navReality = LIVE.navReality || null;

async function liveRefreshAll(opts) {
  const sid = LIVE.sid;
  const token = ++LIVE.refreshToken;
  /* Every exit that did NOT commit leaves an honest reason. A read that lost the session, or that a
     newer read superseded, must not overwrite the newer read's status. */
  const fail = reason => {
    if (LIVE.sid !== sid) return null;
    if (LIVE.refreshToken !== token) return null;
    LIVE.experienceError = reason || 'the latest view could not be loaded';
    return null;
  };
  const stale = () => (LIVE.sid !== sid || LIVE.refreshToken !== token);
  if (IS_DEMO || !sid) return fail('no active live session');

  const expected = (opts && opts.expectCheckpointId) ? String(opts.expectCheckpointId) : '';
  const strictSources = !!(opts && opts.strictSources);

  const readCandidate = async () => {
    const cand = { state: null, evidence: null, artifact: null, nav: null, routes: null,
                   moves: null, readiness: null, experience: null, errors: [] };
    const grab = async (key, fn) => {
      try { cand[key] = await fn(); } catch (e) { cand.errors.push(key); }
    };
    await grab('state', () => API.state(sid));
    if (stale()) return null;
    await grab('evidence', () => API.evidence(sid));
    if (stale()) return null;
    if (cand.state && cand.state.has_diagnosis) await grab('artifact', () => API.diagnosis(sid));
    if (stale()) return null;
    await grab('nav', () => API.navigation(sid));
    if (stale()) return null;
    await grab('routes', async () => {
      let r = await API.routesRead(sid);   // read-only; never births a route on refresh
      if (!(r && (r.routes || []).length) && LIVE.routesBirthTried !== sid) {
        LIVE.routesBirthTried = sid;       // one composition attempt per map, never a loop
        try { await API.routes(sid); } catch (e) { /* keep the honest empty read */ }
        r = await API.routesRead(sid);
      }
      return r;
    });
    if (stale()) return null;
    await grab('moves', () => API.moves(sid));
    if (stale()) return null;
    await grab('readiness', () => API.readiness(sid));
    if (stale()) return null;
    await grab('experience', () => API.experience(sid));
    return cand;
  };

  const mixedSources = cand => {
    const rev = cand.experience && cand.experience.revision
      && cand.experience.revision.projection_revision;
    if (!rev) return ['experience'];
    const bad = [];
    const check = (name, obj) => {
      const pr = obj && obj.reality && obj.reality.projection_revision;
      if (pr && pr !== rev) bad.push(name);
    };
    check('state', cand.state);
    check('navigation', cand.nav);
    check('routes', cand.routes);
    check('readiness', cand.readiness);
    check('moves', cand.moves);            // GET /moves carries its own reality block
    return bad;
  };

  /* The checkpoint a CANDIDATE read model carries. The same precedence as liveCheckpointId, but read
     from the response that is about to be committed instead of from the LIVE globals, so an expected
     checkpoint is verified BEFORE anything is written. */
  const candidateCheckpointId = cand => {
    const rev = (cand.experience && cand.experience.revision) || null;
    if (rev && rev.checkpoint_id) return String(rev.checkpoint_id);
    const cp = (cand.experience && cand.experience.checkpoint) || null;
    if (cp && cp.checkpoint_id) return String(cp.checkpoint_id);
    const reality = (cand.state && cand.state.reality) || null;
    return (reality && reality.checkpoint_id) ? String(reality.checkpoint_id) : '';
  };
  /* Sources whose payload carries the projection revision ('nav' is the navigation read). apply()
     writes only non-null values, so a failed read of any of these keeps its PRE-commit value. */
  const strictKeys = ['state', 'nav', 'routes', 'moves', 'readiness', 'experience'];
  const unreadStrict = cand => strictKeys.filter(k => cand.errors.indexOf(k) !== -1);

  /* The candidate is the ONLY writer of LIVE, and only after validation (and, when the caller named
     an expected checkpoint, after that checkpoint id has been verified on the candidate). */
  const apply = cand => {
    if (cand.state) LIVE.state = cand.state;
    if (cand.evidence) {
      const ev = cand.evidence;
      LIVE.msgs = (ev.transcript || []).map(m => ({ role: (m[0] || m.role) === 'user' ? 'user' : 'engine', text: String(m[1] != null ? m[1] : (m.text || '')) }));
      LIVE.evidence = ev.evidence || []; LIVE.tags = ev.intent_tags || [];
    }
    if (cand.artifact) { LIVE.artifact = cand.artifact; LIVE.explain = null; LIVE.explainState = 'idle'; }
    if (cand.nav) { LIVE.nav = { move: cand.nav.move, summary: cand.nav.summary, current: cand.nav.current || null }; LIVE.navReality = cand.nav.reality || null; }
    if (cand.routes) LIVE.routes = cand.routes;
    if (cand.moves) LIVE.moves = cand.moves;
    if (cand.readiness) LIVE.projection = cand.readiness;
    if (cand.experience) { LIVE.experience = cand.experience; LIVE.experienceError = null; }
  };

  /* Validate one read; on a mixed revision re-read the WHOLE projection once. When the caller asked
     for strict sources, a failed read of any revision-carrying source fails the candidate instead of
     leaving that source at its pre-commit value. */
  const readConsistent = async () => {
    let cand = await readCandidate();
    if (!cand || stale()) return { error: 'refresh stopped before it finished' };
    if (!cand.experience || !cand.state) {
      return { error: 'refresh incomplete: ' + (cand.errors.join(', ') || 'missing experience/state') };
    }
    if (strictSources) {
      const unread = unreadStrict(cand);
      if (unread.length) return { error: 'refresh incomplete: could not read ' + unread.join(', ') };
    }
    let mism = mixedSources(cand);
    if (mism.length) {
      cand = await readCandidate();        // retry the WHOLE read once
      if (!cand || stale()) return { error: 'refresh stopped before it finished' };
      if (!cand.experience || !cand.state) {
        return { error: 'refresh incomplete after retry: ' + (cand.errors.join(', ') || 'missing experience/state') };
      }
      if (strictSources) {
        const unread = unreadStrict(cand);
        if (unread.length) return { error: 'refresh incomplete after retry: could not read ' + unread.join(', ') };
      }
      mism = mixedSources(cand);           // recompute the reference from the NEW response
    }
    if (mism.length) return { error: 'mixed revision across ' + mism.join(', ') };
    return { cand: cand };
  };

  const checkpointBefore = liveCheckpointId();

  /* A read is committed only when the candidate carries the expected checkpoint. A mismatch retries
     the READ once (never the mutation) and a second mismatch is reported, never papered over: LIVE
     stays exactly as it was, with an honest error. */
  const readValidated = async () => {
    let got = await readConsistent();
    if (!got.cand) return got;
    if (expected && candidateCheckpointId(got.cand) !== expected) {
      got = await readConsistent();
      if (!got.cand) return got;
      if (candidateCheckpointId(got.cand) !== expected) {
        return { error: 'the expected checkpoint is not in the read model yet' };
      }
    }
    return got;
  };

  let got = null;
  try { got = await readValidated(); } catch (e) { return fail((e && e.message) ? e.message : String(e)); }
  if (!got.cand) return fail(got.error);   // preserve the previous consistent snapshot; render nothing partial
  apply(got.cand);

  const committed = LIVE.experience;
  const checkpointAfter = liveCheckpointId();
  /* A committed read invalidates derived caches that would otherwise keep pre-checkpoint data. */
  const previews = LIVE.reassessPreview;
  if (previews && typeof previews === 'object') {
    try { delete previews[sid]; } catch (e) { previews[sid] = null; }
  }
  LIVE.routesBirthTried = '';
  LIVE.experienceTried = '';
  LIVE.checkpointStale = false;

  /* /experience is not the per-user workspace or the durable check-in ledger. When the accepted
     checkpoint actually moved, re-read those derived sources through their existing loaders. These
     are best effort: a derived failure never fails the already accepted commit. */
  if (checkpointAfter && checkpointAfter !== checkpointBefore) {
    if (typeof liveLoadWorkspace === 'function') {
      try { await liveLoadWorkspace(); } catch (e) { /* derived cache only */ }
    }
    if (typeof liveLoadCheckins === 'function') {
      try { await liveLoadCheckins(); } catch (e) { /* derived cache only */ }
    }
  }

  if (typeof syncStoreFromLive === 'function') {
    try { syncStoreFromLive(); } catch (e) { /* derived store only; the accepted snapshot stands */ }
  }
  if ((!opts || opts.render !== false) && typeof renderScreenKeepingUi === 'function' && STORE.currentScreen) {
    renderScreenKeepingUi(STORE.currentScreen);
  }
  return committed;
}

/* NC-02: run the version-checked refresh after an ACCEPTED mutation and report success HONESTLY.
   The mutation stands; a failed READ marks the projection stale and is never resubmitted. Returns
   true only when THIS call committed a consistent snapshot. */
LIVE.lastRefreshFailed = false;
async function liveRefreshAfterMutation(opts) {
  let exp = null;
  try { exp = await liveRefreshAll(opts); }
  catch (e) {
    LIVE.experienceError = (e && e.message) ? e.message : String(e);
    exp = null;
  }
  const ok = !!exp;
  LIVE.lastRefreshFailed = !ok;
  return ok;
}
/* Maps/Talk wrapper around the ONE refresh boundary after a reassessment was ACCEPTED. It never
   re-POSTs and never throws: the caller must be able to say "the checkpoint is recorded but the view
   could not be loaded" without retrying the expensive synthesis. strictSources keeps that boundary
   atomic: it commits a fully consistent revision or nothing at all. */
async function liveRefreshAfterReassessment(opts) {
  const o = opts || {};
  let ok = false;
  try {
    ok = await liveRefreshAfterMutation({
      render: o.render !== false, expectCheckpointId: o.expectCheckpointId, strictSources: true,
    });
  } catch (e) {
    ok = false;
  }
  return { ok: !!ok, exp: ok ? LIVE.experience : null };
}
/* Read-only reconciliation after an AMBIGUOUS reassessment response (timeout / network). It reads
   GET /checkpoints and never POSTs, so an unknown outcome cannot buy a second synthesis. Status is
   "committed" only when the server's latest checkpoint is the expected one, "moved" when a DIFFERENT
   checkpoint is now latest, "none" when no checkpoint exists, and "unknown" when the read failed or no
   expected checkpoint was named (the commit status stays unknown rather than guessed). mine correlates
   the outcome with the OPERATION that timed out: it is true only for an exact operation_id match, so a
   checkpoint recorded before operation_id existed (null) is never assumed to be ours. */
async function liveReconcileReassessment(expectedCheckpointId, operationId) {
  const expected = String(expectedCheckpointId || '');
  const op = String(operationId || '');
  const sid = LIVE.sid;
  const unknown = (reason, latest) => ({ status: 'unknown', mine: false, checkpoint: null, latest: latest || null, error: reason });
  if (IS_DEMO || !sid) return unknown('no active live session');
  try {
    const data = await API.checkpoints(sid);
    if (LIVE.sid !== sid) return unknown('the map changed while its checkpoints were read');
    const latest = (data && data.latest) || null;
    if (!latest) return { status: 'none', mine: false, checkpoint: null, latest: null, error: null };
    const mine = !!op && String(latest.operation_id || '') === op;   // an empty operationId is never "mine"
    if (!expected) return { status: 'unknown', mine: mine, checkpoint: null, latest: latest, error: 'no expected checkpoint to compare' };
    if (String(latest.checkpoint_id || '') === expected) {
      return { status: 'committed', mine: mine, checkpoint: latest, latest: latest, error: null };
    }
    return { status: 'moved', mine: mine, checkpoint: null, latest: latest, error: null };
  } catch (e) {
    return unknown((e && e.message) ? e.message : String(e));
  }
}
/* Honest, small surface for "your record is saved, the view could not be refreshed". Read-only: the
   retry re-reads the record and never resubmits anything. Empty when there is nothing to say. */
function liveReassessmentStaleHtml() {
  if (!LIVE.lastRefreshFailed && !LIVE.experienceError) return '';
  const saved = !!LIVE.lastRefreshFailed;
  const line = liveExperienceStatusLine()
    || (LIVE.experienceError ? 'The latest view could not be loaded: ' + String(LIVE.experienceError) : '');
  return '<section class="maps-change-summary" role="status" aria-label="Refresh status" data-kind="STALE">'
    + '<div class="mcs-body">'
    + '<div class="section-meta-label">' + (saved ? 'SAVED RECORD' : 'COULD NOT REFRESH') + '</div>'
    + '<h2 class="mcs-title">' + (saved ? 'Your record is saved. The view could not be refreshed.' : 'The latest view could not be loaded.') + '</h2>'
    + (line ? '<p class="mcs-line">' + esc(line) + '</p>' : '')
    + '<p class="mcs-fine">Retrying only reads your record again. Nothing is resubmitted.</p>'
    + '</div>'
    + '<div class="mcs-actions"><button type="button" class="btn-secondary btn-sm" onclick="liveRetryRefresh()">Retry the view</button></div>'
    + '</section>';
}
/* Retry the READ (never the mutation) and say what actually happened. */
async function liveRetryRefresh() {
  const ok = await liveRefreshAfterMutation({ render: false });
  if (ok) {
    STORE.pendingChangeSummary = null;
    showToast('Your workspace is up to date.');
    if (typeof renderScreenKeepingUi === 'function' && STORE.currentScreen) renderScreenKeepingUi(STORE.currentScreen);
  } else {
    showToast('Still could not refresh. Your record is saved - try again shortly.', '', '', 'error');
  }
  return ok;
}
/* Honest status line for a header. Empty when there is nothing to say, never a claim of freshness. */
function liveExperienceStatusLine() {
  const word = liveExperienceStateWord();
  if (word === 'refreshing') return 'Refreshing from your record...';
  if (word === 'stale') return 'Showing the last accepted state - refresh failed: ' + (LIVE.experienceError || 'unknown error');
  return '';
}
/* What the latest accepted revision changed (added / changed / unlocked / closed / links). */
function liveExperienceChangeSet() {
  const g = LIVE.experience && LIVE.experience.graph;
  return (g && g.change_set) || null;
}
/* Typed graph of the latest accepted revision (nodes, edges, unsupported_edges). */
function liveExperienceGraph() {
  return (LIVE.experience && LIVE.experience.graph) || null;
}
/* Canonical timeline in JOURNEY (V4 §5 C59/C60; audit D-08). First sessions previously had no
   per-session view; this renders the SAME durable events the /experience read model carries, in
   server order, with no invented dates. Read-only: it never writes or reinterprets. */
LIVE.experienceTried = LIVE.experienceTried || '';
function liveTimelineEvents() {
  const exp = LIVE.experience;
  return (exp && Array.isArray(exp.journey_events)) ? exp.journey_events : [];
}
function journeyTimelineHtml(events) {
  const all = Array.isArray(events) ? events : [];
  const checkpoint = (LIVE.experience && LIVE.experience.checkpoint) || null;
  const checkpointId = (checkpoint && checkpoint.checkpoint_id) ? String(checkpoint.checkpoint_id) : '';
  const checkpointVersion = (checkpoint && checkpoint.version != null) ? checkpoint.version : null;
  const refsOf = function (e) { return (e && e.refs) || {}; };

  /* Version lookup comes from the server's own checkpoint events: the transition text never parses a
     checkpoint id and never guesses a version that the record does not carry. */
  const versionById = {};
  all.forEach(function (e) {
    const r = refsOf(e);
    if (e && e.kind === 'checkpoint' && r.checkpoint_id) versionById[String(r.checkpoint_id)] = r.version;
  });
  const isCurrentCheckpoint = function (e) {
    const r = refsOf(e);
    if (checkpointId) return String(r.checkpoint_id || '') === checkpointId;
    return checkpointVersion != null && r.version != null && Number(r.version) === Number(checkpointVersion);
  };
  const staleCodes = ((checkpoint && Array.isArray(checkpoint.stale_reasons)) ? checkpoint.stale_reasons : [])
    .map(function (r) { return typeof r === 'string' ? r : ((r && r.change) ? String(r.change) : ''); })
    .filter(function (c, i, arr) { return !!c && arr.indexOf(c) === i; });

  /* A plan window opens at each committed checkpoint. Action events carry an INDEX only, so an index
     row recorded before the current checkpoint belongs to an earlier plan and must be labelled with
     the checkpoint it was recorded against instead of reading as progress of the current plan. */
  const windows = all.filter(function (e) {
    const r = refsOf(e);
    return e && e.kind === 'checkpoint' && e.ts != null && r.checkpoint_id;
  }).map(function (e) {
    const r = refsOf(e);
    return { id: String(r.checkpoint_id), version: r.version, ts: Number(e.ts) };
  }).sort(function (a, b) { return a.ts - b.ts; });
  const currentWindow = checkpointId ? windows.filter(function (w) { return w.id === checkpointId; })[0] : null;
  const currentTs = (checkpoint && checkpoint.ts != null) ? Number(checkpoint.ts)
    : (currentWindow ? currentWindow.ts : null);
  const windowFor = function (ts) {
    let found = null;
    windows.forEach(function (w) { if (w.ts <= ts) found = w; });
    return found;
  };

  const rows = all.slice(-40).map(function (e) {
    const kindKey = String(e.kind || '');
    const kind = kindKey.replace(/_/g, ' ');
    let title = String(e.title || '');
    let detail = String(e.detail || '');
    const when = (e.ts != null) ? new Date(e.ts * 1000).toLocaleString() : 'time not recorded';
    const r = refsOf(e);
    const ref = r.move_id ? ('move ' + r.move_id) : '';

    if (kindKey === 'checkpoint') {
      /* A checkpoint record is a TRANSITION, not a user action. The current row says which version
         it supersedes; older rows keep the server's own words. Stale codes are the server's. */
      const current = isCurrentCheckpoint(e);
      if (current && checkpoint && checkpoint.supersedes
          && String(checkpoint.supersedes) !== String(r.checkpoint_id || checkpointId)) {
        let prevVersion = versionById[String(checkpoint.supersedes)];
        /* The checkpoint events carry the version; if the record is not in this payload, the server's
           own sequential numbering still identifies the immediately preceding version. */
        if (prevVersion == null && checkpointVersion != null && Number(checkpointVersion) > 1) {
          prevVersion = Number(checkpointVersion) - 1;
        }
        const prevWord = (prevVersion != null) ? ('v' + prevVersion) : 'the previous checkpoint';
        const transitionReason = String(checkpoint.reason || title || 'checkpoint');
        detail = 'v' + (r.version != null ? r.version : (checkpointVersion != null ? checkpointVersion : '?'))
          + ' - ' + transitionReason + ' replaces ' + prevWord + ' (superseded)';
      }
      if (current && staleCodes.length) detail += ' · marked stale by ' + staleCodes.join(', ');
    } else if (kindKey === 'action_completed' || kindKey === 'action_outcome') {
      if (currentTs != null && e.ts != null && Number(e.ts) < currentTs) {
        const win = windowFor(Number(e.ts));
        title += (win && win.version != null)
          ? (' - plan from checkpoint v' + win.version)
          : (win ? ' - plan from an earlier checkpoint' : ' - recorded before the first checkpoint');
      }
    }

    return '<li style="font-size:13px;color:var(--ink-2);margin:3px 0">'
      + '<span style="font-weight:600">' + esc(kind) + '</span> '
      + '<span>' + esc(title) + '</span> '
      + ((kindKey === 'checkpoint' && detail) ? '<span>' + esc(detail) + '</span> ' : '')
      + (ref ? '<span style="color:var(--ink-3)">(' + esc(ref) + ')</span> ' : '')
      + '<span style="color:var(--ink-3)">' + esc(when) + '</span></li>';
  }).join('');
  const cap = all.length > 40 ? ' Showing the latest 40 of ' + all.length + '.' : '';
  return '<section class="card-clean" aria-label="Recorded events" style="margin-top:12px">'
    + '<div class="section-meta-label">ON RECORD, IN ORDER</div>'
    + '<p class="j-chart-note">Every accepted event from the durable record for this map.' + cap + '</p>'
    + '<ol style="margin:6px 0 0;padding-left:18px">' + rows + '</ol></section>';
}
function journeyEnsureTimeline() {
  if (IS_DEMO || !LIVE.artifact) return;
  const host = document.querySelector('#j-root .ws-inner');
  if (!host || host.querySelector('.j-timeline')) return;
  const events = liveTimelineEvents();
  if (events.length) {
    const sec = journeyTimelineHtml(events);
    host.insertAdjacentHTML('beforeend', sec.replace('class="card-clean"', 'class="card-clean j-timeline"'));
    return;
  }
  /* One bounded attempt to fetch the read model; experienceTried stops any retry loop. */
  if (!LIVE.experience && !LIVE.experienceError && LIVE.experienceTried !== LIVE.sid) {
    LIVE.experienceTried = LIVE.sid;
    liveLoadExperience().then(function () {
      if (STORE.currentScreen === 'journey') renderScreenKeepingUi('journey');
    });
  }
}

