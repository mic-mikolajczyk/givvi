import { randomUUID } from 'node:crypto'
import { expect, test, type APIRequestContext } from '@playwright/test'

async function register(api: APIRequestContext, origin: string, email: string, language: 'en' | 'pl') {
  const csrfResponse = await api.get(`${origin}/api/auth/csrf`)
  const csrfToken = (await csrfResponse.json()).csrf_token as string
  const response = await api.post(`${origin}/api/auth/register`, {
    data: { name: 'Exchange member', email, password: 'correct horse battery staple', language },
    headers: { Origin: origin, 'X-CSRF-Token': csrfToken },
  })
  expect(response.status(), await response.text()).toBe(201)
  return (await response.json()).csrf_token as string
}

async function postJson(api: APIRequestContext, origin: string, path: string, csrfToken: string, data: object) {
  const response = await api.post(`${origin}/api${path}`, {
    data,
    headers: { Origin: origin, 'X-CSRF-Token': csrfToken },
  })
  expect(response.ok(), await response.text()).toBe(true)
  return response.json()
}

for (const language of ['en', 'pl'] as const) {
  test(`owner manages prioritized gifts in ${language}`, async ({ page }) => {
    const copy = language === 'en' ? {
      signup: 'Create account', events: 'Events', wishlist: 'Wishlist', add: 'Add a gift', giftName: 'Gift name', save: 'Save gift',
      unknown: 'Price unknown', moveUp: 'Move up', edit: 'Edit gift', remove: 'Delete gift',
    } : {
      signup: 'Utwórz konto', events: 'Wydarzenia', wishlist: 'Lista życzeń', add: 'Dodaj prezent', giftName: 'Nazwa prezentu',
      save: 'Zapisz prezent', unknown: 'Nieznana cena', moveUp: 'Przenieś wyżej', edit: 'Edytuj prezent',
      remove: 'Usuń prezent',
    }
    await page.goto('/register')
    await page.getByRole('combobox').selectOption(language)
    await page.locator('input[name="name"]').fill('Wishlist owner')
    await page.locator('input[name="email"]').fill(`wishlist-${randomUUID()}@example.com`)
    await page.locator('input[name="password"]').fill('correct horse battery staple')
    await page.getByRole('button', { name: copy.signup }).click()
    await expect(page.getByRole('heading', { name: copy.events, exact: true })).toBeVisible()
    await page.getByRole('link', { name: copy.wishlist, exact: true }).click()
    await expect(page.getByRole('heading', { name: copy.wishlist, exact: true })).toBeVisible()

    await page.getByRole('button', { name: copy.add }).click()
    await page.locator('input[name="gift_name"]').fill('First idea')
    await page.getByRole('button', { name: copy.save }).click()
    await expect(page.getByText(copy.unknown)).toBeVisible()

    await page.getByRole('button', { name: copy.add }).click()
    await page.locator('input[name="gift_name"]').fill('Second idea')
    await page.locator('input[name="gift_price"]').fill('45.50')
    await page.locator('select[name="gift_currency"]').selectOption('PLN')
    await page.getByRole('button', { name: copy.save }).click()
    await expect.poll(() => page.locator('.wishlist-gift strong').allTextContents()).toEqual(['First idea', 'Second idea'])

    await page.getByRole('button', { name: `${copy.moveUp} Second idea` }).click()
    await expect.poll(() => page.locator('.wishlist-gift strong').allTextContents()).toEqual(['Second idea', 'First idea'])
    await page.getByRole('button', { name: `${copy.edit} Second idea` }).click()
    await page.locator('input[name="gift_name"]').fill('Updated idea')
    await page.getByRole('button', { name: copy.save }).click()
    await expect(page.getByText('Updated idea')).toBeVisible()

    page.once('dialog', (dialog) => dialog.accept())
    await page.getByRole('button', { name: `${copy.remove} First idea` }).click()
    await expect(page.getByText('First idea')).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath(`wishlist-${language}.png`), fullPage: true })
  })
}

for (const language of ['en', 'pl'] as const) {
  test(`event member views another participant wishlist in ${language}`, async ({ page, browser }) => {
    const origin = `http://127.0.0.1:${process.env.GIVVI_E2E_WEB_PORT || '5173'}`
    const copy = language === 'en' ? {
      signupLanguage: 'en', viewWishlist: 'View wishlist', overBudget: 'Over event budget', back: 'Back to event',
    } : {
      signupLanguage: 'pl', viewWishlist: 'Zobacz listę życzeń', overBudget: 'Powyżej budżetu wydarzenia', back: 'Wróć do wydarzenia',
    }
    const adminEmail = `wishlist-admin-${randomUUID()}@example.com`
    const viewerEmail = `wishlist-viewer-${randomUUID()}@example.com`
    const adminCsrf = await register(page.request, origin, adminEmail, language)
    await postJson(page.request, origin, '/wishlist/gifts', adminCsrf, { name: 'Admin gift' })
    const eventResponse = await postJson(page.request, origin, '/events', adminCsrf, {
      name: 'Winter exchange', exchange_date: '2026-12-20', time_zone: 'UTC', currency: 'EUR', budget: '25.00',
    })
    const eventId = eventResponse.event.id as string
    const adminEntry = await postJson(page.request, origin, `/events/${eventId}/participants`, adminCsrf, { name: 'Admin' })
    const viewerEntry = await postJson(page.request, origin, `/events/${eventId}/participants`, adminCsrf, { name: 'Viewer' })
    const invite = await postJson(page.request, origin, `/events/${eventId}/invite-link`, adminCsrf, {})
    const token = new URL(invite.link as string).hash.slice('#token='.length)
    await postJson(page.request, origin, `/events/${eventId}/claim`, adminCsrf, {
      participant_id: adminEntry.participant.id, token,
    })

    const viewerContext = await browser.newContext()
    const viewerApi = viewerContext.request
    try {
      const viewerCsrf = await register(viewerApi, origin, viewerEmail, language)
      await postJson(viewerApi, origin, '/wishlist/gifts', viewerCsrf, {
        name: 'Over-budget idea', price: '30.00', currency: 'EUR',
      })
      await postJson(viewerApi, origin, `/events/${eventId}/claim`, viewerCsrf, {
        participant_id: viewerEntry.participant.id, token,
      })

      await page.goto(`/events/${eventId}`)
      await expect(page.getByRole('heading', { name: 'Winter exchange' })).toBeVisible()
      await page.getByRole('link', { name: `${copy.viewWishlist} Viewer` }).click()
      await expect(page.getByRole('heading', { name: 'Viewer' })).toBeVisible()
      await expect(page.getByText('Over-budget idea')).toBeVisible()
      await expect(page.getByText(copy.overBudget)).toBeVisible()
      await expect(page.getByRole('button', { name: 'Add a gift' })).toHaveCount(0)
      await expect(page.getByRole('link', { name: copy.back })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.screenshot({ path: test.info().outputPath(`event-wishlist-${language}.png`), fullPage: true })
    } finally {
      await viewerContext.close()
    }
  })
}