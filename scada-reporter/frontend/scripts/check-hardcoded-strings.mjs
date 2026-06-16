import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

// Turkish-specific characters signal un-extracted UI strings that should live
// in the i18n JSON catalogs instead of being hardcoded in components.
const TR_CHARS = /[şğıçöüŞĞİÇÖÜ]/
const SRC = fileURLToPath(new URL('../src', import.meta.url))

// Files that legitimately contain Turkish characters and are NOT migration misses:
const ALLOWLIST = [
  // Concurrent feature (Excel template-fill) — owns its own i18n pass, pending.
  'pages/ExcelTemplates.tsx',
  // Native language name "Türkçe" in the language switcher — must stay literal.
  'components/LanguageSelector.tsx',
  // The following carry Turkish ONLY in code comments (not UI), not user-facing:
  'api/client.ts',
  'main.tsx',
  'context/SettingsContext.tsx',
  'components/SortHeader.tsx',
  'hooks/useSortable.ts',
  'hooks/useLatestStream.ts',
]

function isAllowed(p) {
  return ALLOWLIST.some((a) => p.replace(/\\/g, '/').includes(a))
}

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      if (!p.includes('i18n')) walk(p)
      continue
    }
    if (!/\.(tsx|ts)$/.test(p) || p.endsWith('.test.ts') || p.endsWith('.test.tsx')) continue
    if (isAllowed(p)) continue
    const lines = readFileSync(p, 'utf8').split('\n')
    lines.forEach((line, i) => {
      if (TR_CHARS.test(line)) {
        console.error(`${p}:${i + 1}: ${line.trim()}`)
        process.exitCode = 1
      }
    })
  }
}

walk(SRC)

if (process.exitCode === 1) {
  console.error(
    '\nMove these strings into src/i18n/locales/*/<namespace>.json (or allowlist concurrent-feature files).',
  )
}
