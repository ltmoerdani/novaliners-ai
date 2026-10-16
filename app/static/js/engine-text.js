/* Engine text -> UI language.
 *
 * The engine ships every sentence it writes for a person (check titles, unlock conditions, reasons, path basis,
 * advisory) per language, next to the Indonesian text it computes with (`i18n`, `presentation`, `*_i18n`). This file
 * only PICKS a language: no sentence is written, translated or matched by its wording here, and nothing is keyed by
 * an engine string. A sentence the engine has no UI-language version of passes through unchanged and is tagged
 * lang="id" by trText() so it stays honest for screen readers instead of being silently guessed.
 * (internal-docs §Requirement Presentation; internal-docs UI language.)
 */
const UI_LANG = 'en';

/* row.i18n[UI_LANG][field] when the engine wrote it, else the engine's own text. */
function pickText(row, field) {
  const t = row && row.i18n && row.i18n[UI_LANG] && row.i18n[UI_LANG][field];
  return t || (row && row[field]) || '';
}

function trEngine(text) { return String(text == null ? '' : text).trim(); }

/* Wrap a possibly-untranslated engine sentence: Indonesian leftovers keep lang="id". */
function trText(text) {
  const raw = trEngine(text);
  return /\b(yang|dan|belum|untuk|dari|dengan|Anda|klien|jalur)\b/i.test(raw)
    ? `<span lang="id">${esc(raw)}</span>`
    : esc(raw);
}
