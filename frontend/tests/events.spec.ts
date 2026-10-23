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
    await expect(page.getByText(copy.unclaimed, { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: test.info().outputPath(`events-${language}.png`), fullPage: true })
  })
}

for (const language of ['en', 'pl'] as const) {
  test(`invitee registers and claims a roster entry in ${language}`, async ({ page }) => {
    test.setTimeout(120000)
    const copy = language === 'en' ? {
      signup: 'Create account', create: 'Create event', save: 'Save event', add: 'Add to roster',
      rosterName: 'Roster name', createLink: 'Create link', chooseName: 'Choose your roster name',
      available: 'Available', claim: 'Claim this name', claimed: 'Claimed',
    } : {
      signup: 'Utwórz konto', create: 'Utwórz wydarzenie', save: 'Zapisz wydarzenie', add: 'Dodaj do listy',
      rosterName: 'Imię na liście', createLink: 'Utwórz link', chooseName: 'Wybierz swoje imię z listy',
      available: 'Dostępne', claim: 'Wybierz to imię', claimed: 'Potwierdzono udział',
    }
    const adminEmail = `invite-admin-${randomUUID()}@example.com`
    const inviteeEmail = `invitee-${randomUUID()}@example.com`
    const password = 'correct horse battery staple'
    await page.goto('/register')
    await page.getByRole('combobox').selectOption(language)
    await page.locator('input[name="name"]').fill('Organizer')
    await page.locator('input[name="email"]').fill(adminEmail)
    await page.locator('input[name="password"]').fill(password)
    await page.getByRole('button', { name: copy.signup }).click()
    await expect(page.getByRole('heading', { name: language === 'en' ? 'Events' : 'Wydarzenia', exact: true })).toBeVisible()

    await page.getByRole('button', { name: copy.create }).click()
    await page.locator('input[name="name"]').fill('Winter exchange')
    await page.locator('input[name="exchange_date"]').fill('2026-12-20')
    await page.locator('input[name="time_zone"]').fill('Europe/Warsaw')
    await page.getByRole('button', { name: copy.save }).click()
    await expect(page.getByRole('heading', { name: 'Winter exchange' })).toBeVisible()
    await page.locator('input[name="participant_name"]').fill('Morgan Lee')
    await page.getByRole('button', { name: copy.add }).click()
    await page.getByRole('button', { name: copy.createLink }).click()

    const invitationLink = await page.locator('input[readonly]').inputValue()
    await page.context().clearCookies()
    await page.goto(invitationLink)
    await expect(page.getByRole('heading', { name: copy.chooseName })).toBeVisible()
    await expect(page.getByText('Morgan Lee')).toBeVisible()
    await expect(page.getByText(copy.available, { exact: true })).toBeVisible()
    await expect(page.getByText('Winter exchange')).toHaveCount(0)
    await expect.poll(() => page.url()).toBe(new URL(invitationLink).origin + new URL(invitationLink).pathname)

    await page.getByRole('link', { name: copy.signup }).click()
    await page.getByRole('combobox').selectOption(language)
    await page.locator('input[name="name"]').fill('Morgan')
    await page.locator('input[name="email"]').fill(inviteeEmail)
    await page.locator('input[name="password"]').fill(password)
    await page.getByRole('button', { name: copy.signup }).click()
    await expect(page.getByRole('heading', { name: copy.chooseName })).toBeVisible()
    await page.getByRole('button', { name: copy.claim }).click()
    await expect(page.getByRole('heading', { name: 'Winter exchange' })).toBeVisible()
    await expect(page.getByText(copy.claimed, { exact: true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

for (const language of ['en', 'pl'] as const) {
  test(`participants privately reveal and reset a draw in ${language}`, async ({ browser, page }, testInfo) => {
    test.setTimeout(120000)
    const copy = language === 'en' ? {
      signup: 'Create account', create: 'Create event', save: 'Save event', add: 'Add to roster',
      createLink: 'Create link', enable: 'Enable drawing', reset: 'Reset drawing',
      reveal: 'Reveal your recipient', ownRecipient: 'Your gift recipient', progress: '3 of 3 recipients revealed',
    } : {
      signup: 'Utwórz konto', create: 'Utwórz wydarzenie', save: 'Zapisz wydarzenie', add: 'Dodaj do listy',
      createLink: 'Utwórz link', enable: 'Włącz losowanie', reset: 'Zresetuj losowanie',
      reveal: 'Odkryj odbiorcę prezentu', ownRecipient: 'Osoba, którą obdarujesz', progress: 'Ujawniono 3 z 3 odbiorców',
    }
    const password = 'correct horse battery staple'
    const contexts = []
    const adminEmail = `draw-admin-${randomUUID()}@example.com`
    await page.goto('/register')
    await page.getByRole('combobox').selectOption(language)
    await page.locator('input[name="name"]').fill('Organizer')
    await page.locator('input[name="email"]').fill(adminEmail)
    await page.locator('input[name="password"]').fill(password)
    await page.getByRole('button', { name: copy.signup }).click()

    await page.getByRole('button', { name: copy.create }).click()
    await page.locator('input[name="name"]').fill(`Private draw ${language}`)
    await page.locator('input[name="exchange_date"]').fill('2026-12-20')
    await page.locator('input[name="time_zone"]').fill('Europe/Warsaw')
    await page.getByRole('button', { name: copy.save }).click()
    await expect(page.getByRole('heading', { name: `Private draw ${language}` })).toBeVisible()
    const eventUrl = page.url()

    const rosterNames = ['Morgan', 'Riley', 'Taylor']
    for (const name of rosterNames) {
      await page.locator('input[name="participant_name"]').fill(name)
      await page.getByRole('button', { name: copy.add }).click()
      await expect(page.getByText(name, { exact: true })).toBeVisible()
    }
    await page.getByRole('button', { name: language === 'en' ? 'Create link' : 'Utwórz link' }).click()
    const invitationLink = await page.locator('input[readonly]').inputValue()

    const memberPages = []
    for (const [index, name] of rosterNames.entries()) {
      const context = await browser.newContext({ viewport: page.viewportSize() ?? { width: 1280, height: 720 } })
      contexts.push(context)
      const memberPage = await context.newPage()
      memberPages.push({ page: memberPage, name })
      await memberPage.goto(invitationLink)
      await memberPage.getByRole('combobox').selectOption(language)
      await expect(memberPage.getByRole('heading', {
        name: language === 'en' ? 'Choose your roster name' : 'Wybierz swoje imię z listy',
      })).toBeVisible()
      await memberPage.getByRole('link', { name: copy.signup }).click()
      await memberPage.getByRole('combobox').selectOption(language)
      await memberPage.locator('input[name="name"]').fill(name)
      await memberPage.locator('input[name="email"]').fill(`draw-member-${index}-${randomUUID()}@example.com`)
      await memberPage.locator('input[name="password"]').fill(password)
      await memberPage.getByRole('button', { name: copy.signup }).click()
      await expect(memberPage.getByRole('heading', {
        name: language === 'en' ? 'Choose your roster name' : 'Wybierz swoje imię z listy',
      })).toBeVisible()
      await memberPage.getByRole('listitem').filter({ hasText: name }).getByRole('button', {
        name: language === 'en' ? 'Claim this name' : 'Wybierz to imię',
      }).click()
      await expect(memberPage.getByRole('heading', { name: `Private draw ${language}` })).toBeVisible()
    }

    await page.goto(eventUrl)
    await expect(page.getByRole('button', { name: copy.enable })).toBeEnabled()
    await page.getByRole('button', { name: copy.enable }).click()
    await expect(page.getByRole('button', { name: copy.reset })).toBeVisible()
    page.once('dialog', (dialog) => dialog.accept())
    await page.getByRole('button', { name: copy.reset }).click()
    await expect(page.getByRole('button', { name: copy.enable })).toBeVisible()
    await page.getByRole('button', { name: copy.enable }).click()

    const revealedRecipients = []
    for (const member of memberPages) {
      await member.page.reload()
      await member.page.getByRole('button', { name: copy.reveal }).click()
      await expect(member.page.getByText(copy.ownRecipient)).toBeVisible()
      const recipient = await member.page.locator('.recipient-reveal strong').innerText()
      expect(recipient).not.toBe(member.name)
      revealedRecipients.push(recipient)
    }
    expect(new Set(revealedRecipients).size).toBe(rosterNames.length)
    expect(new Set(revealedRecipients)).toEqual(new Set(rosterNames))

    await page.reload()
    await expect(page.getByText(copy.progress)).toBeVisible()
    await expect(page.getByRole('button', { name: copy.reset })).toHaveCount(0)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: testInfo.outputPath(`drawing-${language}.png`), fullPage: true })
    await Promise.all(contexts.map((context) => context.close()))
  })
}