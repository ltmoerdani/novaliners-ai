// Copy and slop guard, run against whatever is on screen. Shared by copy.spec.mjs (demo, every scene, light and dark)
// and live.spec.mjs (every screenshot step of the real flow).
// Rules come from docs/03-architecture-tech/07-konvensi-bahasa-ui.md (English UI, vocabulary lock, no em dash in product copy)
// and the v11 design (record D1, D3): no emoji as icons, no exclamation marks, no banned product wording, no Indonesian in the
// chrome, only the four path words in capitals as statuses. The v11 eyebrow style (small uppercase, tracked captions) is part of
// the design, so it is allowed; the v9 rule against it was retired with the v9 shell (record §3).
// live: true skips the em dash, exclamation and Indonesian checks, because in the real flow those words come from the engine or
// the model or the person, not from the UI.

// Status pills: the four path words (docs 02/03 §6.2, record DoD 6) plus the move and flow chips of the product. A pill saying
// anything else in capitals (ABSENT, a new word of the model's) is a new status vocabulary and must be decided, not slipped in.
// GO SMALL, GO, SCALE, SAFETY FIRST, FIRST TEST and START SMALL are the verdict of the diagnosis (the engine's decision spectrum on the
// reveal), not a path status; a pill that is a sentence ("Keeps Rp20M in your pocket") or a neutral hold note is copy, not a status.
const PILL_OK = /^(?:● )?(STOP|NOT YET|TEST FIRST|OPEN|(OPEN|NOT YET|TEST FIRST|STOP)( · [A-Z0-9 ]+)?|READY|READY TO MOVE|TODO|DONE|WAITING|IN PROGRESS|IN FOCUS|PROOF NEEDED|NOT FINAL YET|ON HOLD|RECOMMENDED( · [A-Z ]+)?|ACTIVE|PAUSED|STOPPED BY YOU|HERE|GOAL|NEW|NOW|GO SMALL|GO|SCALE|SAFETY FIRST|FIRST TEST|START SMALL)$/i;
const ID_WORDS = /\b(yang|untuk|dengan|tidak|belum|sudah|selamat|kirim|simpan|lanjut|kembali|beranda|halaman|pengguna|jangan|tolong|silakan|terima kasih)\b/i;

export async function scanCopy(page, { live = false } = {}) {
  return page.evaluate(([pillOkSrc, idSrc, live]) => {
    const pillOk = new RegExp(pillOkSrc, 'i'), idWords = new RegExp(idSrc, 'i');
    const out = [];
    const vis = el => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
    const skip = el => el.closest('#proto-widget, #proto-widget-card, script, style, [hidden], .msg-draft, svg, .logo-dark');
    // what the person wrote, a message draft they may send in their language, and the model's own words are content, not chrome
    const content = el => el.closest('.msg-box, .talk-bubble, .talk-msg, #engine-settings, .v11-map-list, .v11-topbar-map, .brief-text, .diag-quote');
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const el = n.parentElement; const t = n.nodeValue.replace(/\s+/g, ' ').trim();
      if (!t || !el || skip(el) || !vis(el)) continue;
      if (/\p{Extended_Pictographic}/u.test(t.replace(/[✓✕✔✖↗↘→←↑↓↺]/g, ''))) out.push(`emoji: "${t.slice(0, 50)}"`);
      if (!live && !content(el)) {
        if (/!/.test(t)) out.push(`exclamation: "${t.slice(0, 60)}"`);
        if (/ — /.test(t)) out.push(`em dash: "${t.slice(0, 60)}"`);
        const m = t.match(idWords); if (m) out.push(`Indonesian "${m[0]}": "${t.slice(0, 60)}"`);
      }
      if (/\b(Revenue Navigator|AI REVENUE|START SMALL|Start my analysis|instant results|All projects|dashboard)\b/i.test(t)) out.push(`banned wording: "${t.slice(0, 60)}"`);
      if (!content(el) && /\bcycles?\b/i.test(t)) out.push(`old vocabulary "cycle": "${t.slice(0, 60)}"`);
    }
    for (const el of document.querySelectorAll('.status-pill')) {
      if (skip(el) || !vis(el) || el.classList.contains('hold')) continue;
      const t = el.textContent.replace(/\s+/g, ' ').trim();
      if (t && t === t.toUpperCase() && /[A-Z]{3,}/.test(t) && !pillOk.test(t)) out.push(`status pill outside the vocabulary: "${t.slice(0, 40)}"`);
    }
    return [...new Set(out)];
  }, [PILL_OK.source, ID_WORDS.source, live]);
}
