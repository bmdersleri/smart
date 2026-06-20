import { test, expect, type Page } from '@playwright/test'

// Default seeded admin (just seed-users).
const USER = 'admin'
const PASS = 'admin123'

/** The language <select> — identified by its options, so it's locale-proof. */
function langSelect(page: Page) {
  return page.locator('select:has(option[value="en"])')
}

/** Read a stat card's big value by its (case-insensitive) label text. */
function cardValue(page: Page, label: string) {
  return page
    .locator('p.uppercase', { hasText: new RegExp(label, 'i') })
    .locator('xpath=following-sibling::div[1]//p')
    .first()
}

async function login(page: Page) {
  await page.goto('/')
  await page.fill('input[autocomplete="username"]', USER)
  await page.fill('input[type="password"]', PASS)
  await page.click('button[type="submit"]')
  // The language selector only exists in the authenticated layout — and its
  // text is localized (admin may default to any language), so key off the
  // <select>'s options rather than any visible label.
  await expect(langSelect(page)).toBeVisible({ timeout: 15_000 })
}

test.describe('Dashboard overview', () => {
  test('stat cards render live data in English (no em-dash)', async ({ page }) => {
    await login(page)
    // Force English so percent placement is deterministic.
    await langSelect(page).selectOption('en')

    // Cards are fed by /overview (10s polling) — wait for real values.
    const activeTags = cardValue(page, 'Active Tags')
    await expect(activeTags).not.toHaveText('—', { timeout: 15_000 })
    await expect(activeTags).toHaveText(/^\d[\d,]*$/)

    // English locale: percent AFTER the number (regression guard for the
    // hard-coded "%100" Turkish placement).
    const quality = cardValue(page, 'Data Quality')
    await expect(quality).toHaveText(/^\d[\d.,]*%$/)

    const deadband = cardValue(page, 'Deadband Savings')
    await expect(deadband).toHaveText(/%$/)

    // None of the overview cards should be empty.
    for (const label of ['24-Hour Readings', 'Last 1 Hour', 'Last Data']) {
      await expect(cardValue(page, label)).not.toHaveText('—')
    }
  })

  test('Turkish locale keeps percent before the number', async ({ page }) => {
    await login(page)
    await langSelect(page).selectOption('tr')
    // tr convention: %100 / %92,9
    await expect(cardValue(page, 'Veri Kalitesi')).toHaveText(/^%\d/, { timeout: 15_000 })
  })
})
