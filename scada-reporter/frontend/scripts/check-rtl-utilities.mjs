import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

// Physical (direction-locked) Tailwind flow utilities break RTL — use logical
// equivalents instead so Arabic mirrors correctly while LTR stays identical:
//   text-left→text-start  text-right→text-end
//   ml-*→ms-*  mr-*→me-*  pl-*→ps-*  pr-*→pe-*
//   rounded-l-*→rounded-s-*  rounded-r-*→rounded-e-*
//   border-l*→border-s*  border-r*→border-e*
// NOT flagged: absolute positioning (left-N/right-N), vertical borders
// (border-t/border-b), and radius sizes (rounded-lg/md/etc.).
const PHYS =
  /\b(?:text-(?:left|right)|[mp][lr]-[0-9]|rounded-[lr]-|border-[lr](?:-|\b))/
const SRC = fileURLToPath(new URL('../src', import.meta.url))

function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      if (!p.includes('i18n')) walk(p)
      continue
    }
    if (!/\.(tsx|ts)$/.test(p) || p.endsWith('.test.ts') || p.endsWith('.test.tsx')) continue
    const lines = readFileSync(p, 'utf8').split('\n')
    lines.forEach((line, i) => {
      if (PHYS.test(line)) {
        console.error(`${p}:${i + 1}: ${line.trim()}`)
        process.exitCode = 1
      }
    })
  }
}

walk(SRC)

if (process.exitCode === 1) {
  console.error(
    '\nReplace physical directional utilities with logical ones (ms/me/ps/pe, text-start/end, rounded-s/e, border-s/e) so RTL mirrors. See scripts/check-rtl-utilities.mjs header.',
  )
}
