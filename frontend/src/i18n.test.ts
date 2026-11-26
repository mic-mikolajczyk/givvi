import { expect, it } from 'vitest'

import { i18n, messages } from './i18n'

function keys(value: object, prefix = ''): string[] {
  return Object.entries(value).flatMap(([key, entry]) => typeof entry === 'string' ? [`${prefix}${key}`] : keys(entry, `${prefix}${key}.`))
}

it('provides every message in English and Polish', () => {
  expect(keys(messages.pl).sort()).toEqual(keys(messages.en).sort())
})

it('defaults to Polish', () => {
  expect(i18n.global.locale.value).toBe('pl')
})
