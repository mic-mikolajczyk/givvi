import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'

for (const language of ['en', 'pl'] as const) {
  test(`organizer creates an event and prepares its roster in ${language}`, async ({ page }) => {
    const copy = language === 'en' ? {
      signup: 'Create account', events: 'Events', create: 'Create event', name: 'Event name',
      date: 'Exchange date', zone: 'Time zone', save: 'Save event', participant: 'Roster name',
      add: 'Add to roster', unclaimed: 'Not claimed', roster: 'Participant roster',
    } : {
      signup: 'Utwórz konto', events: 'Wydarzenia', create: 'Utwórz wydarzenie', name: 'Nazwa wydarzenia',
      date: 'Data wymiany', zone: 'Strefa czasowa', save: 'Zapisz wydarzenie', participant: 'Imię na liście',
      add: 'Dodaj do listy', unclaimed: 'Niepotwierdzony', roster: 'Lista uczestników',
    }
    const email = `phase2-${randomUUID()}@example.com`
    await page.goto('/register')
    await page.getByRole('combobox').selectOption(language)
    await page.locator('input[name="name"]').fill('Organizer')
    await page.locator('input[name="email"]').fill(email)
    await page.locator('input[name="password"]').fill('correct horse battery staple')
    await page.getByRole('button', { name: copy.signup }).click()
    await expect(page.getByRole('heading', { name: copy.events, exact: true })).toBeVisible()

    await page.getByRole('button', { name: copy.create }).click()
    await page.locator('input[name="name"]').fill(`Winter exchange ${language}`)
    await page.locator('input[name="exchange_date"]').fill('2026-12-20')
    await page.locator('input[name="time_zone"]').fill('Europe/Warsaw')
    await page.getByRole('button', { name: copy.save }).click()
    await expect(page.getByRole('heading', { name: `Winter exchange ${language}` })).toBeVisible()

    await page.locator('input[name="participant_name"]').fill('Morgan Lee')
    await page.getByRole('button', { name: copy.add }).click()
    await expect(page.getByRole('heading', { name: copy.roster })).toBeVisible()
    await expect(page.getByText('Morgan Lee')).toBeVisible()
    await expect(page.getByText(copy.unclaimed)).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath(`events-${language}.png`), fullPage: true })
  })
}