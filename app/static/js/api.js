/* Backend client. Thin wrappers over the existing FastAPI endpoints (no new server contract). */
const API = {
  async raw(url, opts) {
    const r = await fetch(url, opts);
    const text = await r.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { /* non-JSON error body */ }
    if (!r.ok) {
      const detail = data && (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
      const err = new Error(detail || text.slice(0, 160) || ('HTTP ' + r.status));
      err.status = r.status;
      /* Phase 6.1 (NC-R2): a guarded refusal carries a MACHINE code plus the fresh server facts
         (eligibility, preview, checkpoint). The UI renders those codes and those facts; it never
         invents a reason of its own and never turns a technical failure into a business verdict. */
      err.code = (data && data.detail && typeof data.detail === 'object' && data.detail.code) || '';
      err.detail = (data && data.detail && typeof data.detail === 'object') ? data.detail : null;
      throw err;
    }
    return data;
  },
  get(url, opts) { return API.raw(url, opts); },
  post(url, body, opts) {
    return API.raw(url, Object.assign({
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body)
    }, opts || {}));
  },
  health: () => API.get('/health'),
  switchEngine: body => API.post('/admin/model', body),
  createSession: body => API.post('/session', body),
  // idempotency_key is STABLE per logical send: a resend (retry) uses the same key so there is no
  // duplicate event/effect (R3.2). moveId = this message is an OBSERVATION OF THE RESULT of a Move (R6).
  message: (sid, text, key, moveId) => API.post(`/session/${sid}/message`,
    Object.assign({ text }, key ? { idempotency_key: key } : {}, moveId ? { move_id: moveId } : {})),
  // MC01-2: reasoning-only recovery for a DEGRADED turn — the user's story is NOT resent;
  // the server reruns navigation+reasoning over the State already accepted.
  retryReasoning: sid => API.post(`/session/${sid}/retry_reasoning`, {}),
  checkpoints: sid => API.get(`/session/${sid}/checkpoints`),
  reassess: sid => API.post(`/session/${sid}/reassess`),
  // Phase 6.1 (NC-R1/NC-R4): the EXPLICITLY CONFIRMED reassessment. The operation key travels WITH
  // the write (D-10 pattern), so a double-click, a re-render or a retry after an ambiguous timeout
  // replays the accepted checkpoint instead of buying a second synthesis; the approved checkpoint and
  // revision are preconditions the server rechecks at POST time and refuses with 409 if they moved.
  reassessConfirm: (sid, body, opts) => API.post(`/session/${sid}/reassess`, body, opts),
  moves: sid => API.get(`/session/${sid}/moves`),
  moveEvent: (sid, moveId, event, note) => API.post(`/session/${sid}/moves/${encodeURIComponent(moveId)}/events`, { event, note: note || '' }),
  finalize: (sid, signal) => API.post(`/session/${sid}/finalize`, undefined, { signal }),
  diagnosis: sid => API.get(`/session/${sid}/diagnosis`),
  explain: sid => API.get(`/session/${sid}/explain`),
  state: sid => API.get(`/session/${sid}/state`),
  evidence: sid => API.get(`/session/${sid}/evidence`),
  progress: sid => API.get(`/session/${sid}/progress`),
  navigation: sid => API.get(`/session/${sid}/navigation`),
  journey: sid => API.get(`/session/${sid}/journey`),
  sessions: () => API.get('/sessions?limit=20'),
  // D-02: durable check-in history (server), not localStorage. Same null policy: a field that was
  // not reported stays null, never 0; the operation key makes a retry replay instead of duplicate.
  checkins: sid => API.get('/session/' + sid + '/checkins'),
  // MAP-06 Re-evaluate Preview (C08): non-mutating, deterministic; never triggers synthesis.
  reevaluatePreview: sid => API.get('/session/' + sid + '/reevaluate-preview'),
  checkin: (sid, body) => API.post('/session/' + sid + '/checkin', body),
  // V4 §4: version-bound experience read model + canonical same-session timeline (audit D-04/D-05/D-08).
  // String concatenation, not a template literal: keeps this file's contract visible to any reader.
  experience: sid => API.get('/session/' + sid + '/experience'),
  timeline: sid => API.get('/session/' + sid + '/timeline'),
  // D-10: the operation key travels WITH the write, so a retry replays an accepted event instead of
  // appending a second one. A key reused with a different payload is a deterministic 409.
  routeNodeOp: (sid, routeId, nodeId, event, opId) => API.post(
    '/session/' + sid + '/routes/' + encodeURIComponent(routeId) + '/nodes/' + encodeURIComponent(nodeId) + '/execution',
    { event, operation_id: opId || '' }),
  moveEventOp: (sid, moveId, event, note, opId) => API.post(
    '/session/' + sid + '/moves/' + encodeURIComponent(moveId) + '/events',
    { event, note: note || '', operation_id: opId || '' }),
  // Phase 7: ONE action of ONE canonical Move. The move_id and action_id travel in the URL, so the
  // accepted event is bound to that exact action; a retry with the same operation_id replays it.
  moveActionOp: (sid, moveId, actionId, event, note, opId) => API.post(
    '/session/' + sid + '/moves/' + encodeURIComponent(moveId) + '/actions/'
      + encodeURIComponent(actionId) + '/events',
    { event, note: note || '', operation_id: opId || '' }),
  // Phase 7: the result belongs to the Move as a whole - no arbitrary action owns it.
  moveOutcome: (sid, moveId, body) => API.post(
    '/session/' + sid + '/moves/' + encodeURIComponent(moveId) + '/outcome', body),
  workspace: uid => API.get(`/workspace/${encodeURIComponent(uid)}`),
  actionReport: (sid, idx, body) => API.post(`/session/${sid}/action/${idx}/report`, body),
  // Move-centric: ONE outcome for the whole set of actions, and the read-only continuation (what comes next).
  planReport: (sid, body) => API.post(`/session/${sid}/plan/report`, body),
  continuation: sid => API.get(`/session/${sid}/continuation`),
  // Phase 7 §10 case B: the user EXPLICITLY asks the engine to resolve the next authorized state.
  // LLM-backed and never silent; it creates no checkpoint and invents no Move.
  nextMove: sid => API.post('/session/' + sid + '/next_move', {}),
  ask: (sid, body) => API.post(`/session/${sid}/ask`, body),
  routes: sid => API.post(`/session/${sid}/routes`),
  // MAP-06 Rebuild View (C07): a READ that re-projects existing lineage and never births a route.
  routesRead: sid => API.get(`/session/${sid}/routes`),
  readiness: sid => API.get(`/session/${sid}/readiness`),
  routeNode: (sid, routeId, nodeId, event) => API.post(`/session/${sid}/routes/${encodeURIComponent(routeId)}/nodes/${encodeURIComponent(nodeId)}/execution`, { event })
};
