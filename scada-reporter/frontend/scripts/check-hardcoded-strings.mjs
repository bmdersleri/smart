import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

// Turkish-specific characters signal un-extracted UI strings that should live
// in the i18n JSON catalogs instead of being hardcoded in components.
const TR_CHARS = /[şğıçöüŞĞİÇÖÜ]/
const SRC = fileURLToPath(new URL('../src', import.meta.url))

// Files that legitimately contain Turkish characters and are NOT migration misses:
const ALLOWLIST = [
  // Native language name "Türkçe" in the language switcher — must stay literal.
  'components/LanguageSelector.tsx',
  // The following carry Turkish ONLY in code comments (not UI), not user-facing:
  'api/client.ts',
  'main.tsx',
  'context/SettingsContext.tsx',
  'hooks/useSortable.ts',
  'hooks/useLatestStream.ts',
  'hooks/useLogStream.ts',
]

function isAllowed(p) {
  return ALLOWLIST.some((a) => p.replace(/\\/g, '/').includes(a))
}

// --- Pass 2: untranslated English literals in JSX (warning mode) ---------
// Heuristic (no parser): flag letter-bearing literal text that should go
// through t(). Two shapes:
//   1. JSX text children:  >Add new tag<   (a multi-word phrase, not {t(...)})
//   2. UI string attrs:    title="..." placeholder="..." aria-label="..." alt="..."
// Conservative on purpose — only multi-word phrases and the four attrs above
// are flagged, so single technical tokens (PLC, CSV, S7) and {expressions}
// are ignored. JSX braces ({t('x')}, {value}) never match (excluded chars).
const I18N_WARN_MODE = false // Step 4: fail the build once the backlog is zero

// Two+ letter-words separated by whitespace → a human phrase (e.g. "Add Tag").
const PHRASE = /[A-Za-z]{2,}(?:[^<>{}]*?\s[A-Za-z]{2,})/
// Text node: between '>' and the next '<' or '{', containing no tags/braces.
const JSX_TEXT = />([^<>{}]+)[<{]/g
// Static (non-{t()}) UI string attributes.
const ATTR = /\b(?:title|placeholder|aria-label|alt)\s*=\s*"([^"]*[A-Za-z]{2,}[^"]*)"/g
// Code punctuation that never appears in plain UI prose — its presence in a
// captured "text node" means we matched JS/TS code (arrow fns, generics, etc.),
// not real JSX text. Excluding it kills the common false positives.
const CODE_CHARS = /[=`()[\];:]/
// Literal phrases that must NOT be translated (brand/proper nouns).
const PHRASE_ALLOWLIST = ['EKONT SMART REPORT']

const i18nFindings = []

// Is the text node at `idx` inside an inline <code>…</code> (literal commands)?
function insideCode(line, idx) {
  const before = line.slice(0, idx)
  return before.lastIndexOf('<code') > before.lastIndexOf('</code>')
}

function scanI18n(p, line, i) {
  const trimmed = line.trim()
  if (trimmed.startsWith('//') || trimmed.startsWith('*')) return // skip comments
  let m
  JSX_TEXT.lastIndex = 0
  while ((m = JSX_TEXT.exec(line))) {
    const text = m[1].trim()
    if (!PHRASE.test(text)) continue
    if (CODE_CHARS.test(text)) continue // JS/TS code, not prose
    if (PHRASE_ALLOWLIST.includes(text)) continue // brand names
    if (insideCode(line, m.index)) continue // literal CLI commands in <code>
    i18nFindings.push(`${p}:${i + 1}: <text> ${text}`)
  }
  ATTR.lastIndex = 0
  while ((m = ATTR.exec(line))) {
    const val = m[1].trim()
    if (!/\s/.test(val)) continue // single technical token (e.g. placeholder="admin")
    i18nFindings.push(`${p}:${i + 1}: ${m[0].trim()}`)
  }
}

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      // Skip generated (auto-generated code) and i18n (translation catalogs).
      if (p.includes('i18n') || p.replace(/\\/g, '/').includes('api/generated')) continue
      walk(p)
      continue
    }
    if (!/\.(tsx|ts)$/.test(p) || p.endsWith('.test.ts') || p.endsWith('.test.tsx')) continue
    const lines = readFileSync(p, 'utf8').split('\n')
    lines.forEach((line, i) => {
      // Pass 1: Turkish characters (hard fail) — honours the allowlist.
      if (!isAllowed(p) && TR_CHARS.test(line)) {
        console.error(`${p}:${i + 1}: ${line.trim()}`)
        process.exitCode = 1
      }
      // Pass 2: English JSX literals (warning by default).
      if (p.endsWith('.tsx') && !isAllowed(p)) scanI18n(p, line, i)
    })
  }
}

walk(SRC)

if (process.exitCode === 1) {
  console.error(
    '\nMove these strings into src/i18n/locales/*/<namespace>.json (or allowlist concurrent-feature files).',
  )
}

if (i18nFindings.length) {
  const label = I18N_WARN_MODE ? 'warning' : 'error'
  console.error(`\n[i18n ${label}] ${i18nFindings.length} possible untranslated English literal(s):`)
  i18nFindings.forEach((f) => console.error('  ' + f))
  console.error('\nWrap user-facing text in t(...) (add keys to src/i18n/locales/*/<ns>.json).')
  if (!I18N_WARN_MODE) process.exitCode = 1
}
