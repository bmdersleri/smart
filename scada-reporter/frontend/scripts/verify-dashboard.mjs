// Lightweight dashboard verifier using puppeteer-core + the system Chrome
// (no bundled browser download). Logs in, reads the overview stat cards, and
// writes a full-page screenshot.
//
//   node scripts/verify-dashboard.mjs [outfile.png]
//
// Requires frontend on :5173 and backend on :8001. Override the browser with
// CHROME_PATH=... if Chrome/Edge isn't in a default location.
import { existsSync } from 'node:fs'
import puppeteer from 'puppeteer-core'

const CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean)

const executablePath = CANDIDATES.find((p) => existsSync(p))
if (!executablePath) {
  console.error('No Chrome/Edge found. Set CHROME_PATH to the browser executable.')
  process.exit(2)
}

const BASE = process.env.BASE_URL || 'http://localhost:5173'
const OUT = process.argv[2] || 'dashboard.png'

const browser = await puppeteer.launch({
  executablePath,
  headless: 'new',
  args: ['--no-sandbox', '--window-size=1400,1000'],
  defaultViewport: { width: 1400, height: 1000 },
})
const page = await browser.newPage()
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push('console: ' + m.text()))
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))

try {
  await page.goto(BASE + '/', { waitUntil: 'networkidle2', timeout: 30_000 })
  await page.waitForSelector('input[autocomplete="username"]', { timeout: 15_000 })
  await page.type('input[autocomplete="username"]', 'admin')
  await page.type('input[type="password"]', 'admin123')
  await Promise.all([
    page.click('button[type="submit"]'),
    page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 20_000 }).catch(() => {}),
  ])
  await new Promise((r) => setTimeout(r, 6_000)) // let the 10s-polling cards resolve

  const cards = await page.evaluate(() =>
    [...document.querySelectorAll('p.text-2xl')].map((v) => ({
      label: v.closest('div')?.parentElement?.querySelector('p.uppercase')?.textContent?.trim() ?? '',
      value: v.textContent.trim(),
    })),
  )
  await page.screenshot({ path: OUT, fullPage: true })
  console.log(JSON.stringify({ url: page.url(), cards, errors }, null, 2))
} catch (e) {
  console.log(JSON.stringify({ fatal: String(e), errors }, null, 2))
  process.exitCode = 1
} finally {
  await browser.close()
}
