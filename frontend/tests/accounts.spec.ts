import { randomUUID } from 'node:crypto'
import { expect, test, type APIRequestContext } from '@playwright/test'

async function emailLink(request: APIRequestContext, recipient: string, kind: string) {
  let link = ''
  await expect.poll(async () => {
    const listing = await request.get('http://127.0.0.1:8025/api/v1/messages')
    const payload = await listing.json()
    for (const message of payload.messages) {
      if (!message.To.some((address: { Address: string }) => address.Address === recipient)) continue
      const detail = await request.get(`http://127.0.0.1:8025/api/v1/message/${message.ID}`)
      const body = (await detail.json()).Text as string
      const candidate = body.split('\n').find((line) => line.trim().startsWith('http://'))?.trim()
      if (candidate && new URL(candidate).pathname === `/${kind}`) { link = candidate; return true }
    }
    return false
  }, { timeout: 30000 }).toBe(true)
  return link
}

for (const language of ['en', 'pl'] as const) {
  test(`account lifecycle in ${language}`, async ({ page, request }) => {
    test.setTimeout(120000)
    const email = `phase1-${randomUUID()}@example.com`
    const changedEmail = `changed-${randomUUID()}@example.com`
    const password = 'correct horse battery staple'
    const copy = language === 'en' ? {
      signup: 'Create account', inbox: 'Check your inbox', verify: 'Verify email', verified: 'Email verified',
      login: 'Sign in', events: 'Events', profile: 'Profile', save: 'Save', saved: 'Profile saved',
      emailChange: 'Change email', passwordChange: 'Change password', logout: 'Log out', reset: 'Send reset link',
      newPassword: 'Set new password', passwordUpdated: 'Password updated',
    } : {
      signup: 'Utwórz konto', inbox: 'Sprawdź skrzynkę odbiorczą', verify: 'Potwierdź email', verified: 'Email potwierdzony',
      login: 'Zaloguj się', events: 'Wydarzenia', profile: 'Profil', save: 'Zapisz', saved: 'Profil zapisany',
      emailChange: 'Zmień email', passwordChange: 'Zmień hasło', logout: 'Wyloguj się', reset: 'Wyślij link',
      newPassword: 'Ustaw nowe hasło', passwordUpdated: 'Hasło zmienione',
    }
    await page.goto('/register')
    await page.getByRole('combobox').selectOption(language)
    await page.locator('input[name="name"]').fill('Alicja')
    await page.locator('input[name="email"]').fill(email)
    await page.locator('input[name="password"]').fill(password)
    await page.getByRole('button', { name: copy.signup }).click()
    await expect(page.getByRole('status')).toHaveText(copy.inbox)

    await page.goto(await emailLink(request, email, 'verify'))
    await expect(page).not.toHaveURL(/#token=/)
    await page.getByRole('button', { name: copy.verify }).click()
    await expect(page.getByRole('status')).toHaveText(copy.verified)
    await page.getByRole('link', { name: copy.login, exact: true }).click()
    await page.locator('input[name="email"]').fill(email)
    await page.locator('input[name="password"]').fill(password)
    await page.getByRole('button', { name: copy.login }).click()
    await expect(page.getByRole('heading', { name: copy.events, exact: true })).toBeVisible()

    await page.getByRole('link', { name: copy.profile, exact: true }).click()
    await page.locator('input[name="name"]').fill('Alicja Nowak')
    await page.getByRole('button', { name: copy.save, exact: true }).click()
    await expect(page.getByRole('status')).toHaveText(copy.saved)
    await page.screenshot({ path: test.info().outputPath(`profile-${language}.png`), fullPage: true })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)

    await page.locator('input[name="email"]').fill(changedEmail)
    await page.locator('input[name="email-password"]').fill(password)
    await page.getByRole('button', { name: copy.emailChange, exact: true }).click()
    await expect(page.getByRole('status')).toHaveText(copy.inbox)
    await page.goto(await emailLink(request, changedEmail, 'verify'))
    await page.getByRole('button', { name: copy.verify }).click()
    await expect(page.getByRole('status')).toHaveText(copy.verified)
    await page.getByRole('link', { name: copy.login, exact: true }).click()
    await page.locator('input[name="email"]').fill(changedEmail)
    await page.locator('input[name="password"]').fill(password)
    await page.getByRole('button', { name: copy.login }).click()
    await page.getByRole('link', { name: copy.profile, exact: true }).click()
    await page.locator('input[name="current-password"]').fill(password)
    await page.locator('input[name="new-password"]').fill('a changed correct password')
    await page.getByRole('button', { name: copy.passwordChange, exact: true }).click()
    await expect(page).toHaveURL(/\/login/)
    await page.locator('input[name="email"]').fill(changedEmail)
    await page.locator('input[name="password"]').fill('a changed correct password')
    await page.getByRole('button', { name: copy.login }).click()
    await page.getByRole('link', { name: copy.profile, exact: true }).click()
    await page.getByRole('button', { name: copy.logout }).click()
    await expect(page).toHaveURL(/\/login/)

    await page.goto('/forgot-password')
    await page.locator('input[name="email"]').fill(changedEmail)
    await page.getByRole('button', { name: copy.reset }).click()
    await expect(page.getByRole('status')).toHaveText(copy.inbox)
    await page.goto(await emailLink(request, changedEmail, 'reset-password'))
    await page.locator('input[name="password"]').fill('a recovered correct password')
    await page.getByRole('button', { name: copy.newPassword }).click()
    await expect(page.getByRole('status')).toHaveText(copy.passwordUpdated)
    await page.getByRole('link', { name: copy.login, exact: true }).click()
    await page.locator('input[name="email"]').fill(changedEmail)
    await page.locator('input[name="password"]').fill('a recovered correct password')
    await page.getByRole('button', { name: copy.login }).click()
    await expect(page.getByRole('heading', { name: copy.events, exact: true })).toBeVisible()
    await page.getByRole('link', { name: language === 'en' ? 'Wishlist' : 'Lista życzeń', exact: true }).click()
    await expect(page.getByRole('heading')).toBeVisible()
  })
}
