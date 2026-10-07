import { createI18n } from 'vue-i18n'

export const messages = {
  en: {
    statusTitle: 'Service status',
    checking: 'Checking',
    connected: 'Connected',
    unavailable: 'Unavailable',
    retry: 'Check again',
    language: 'Language',
  },
  pl: {
    statusTitle: 'Stan usługi',
    checking: 'Sprawdzanie',
    connected: 'Połączono',
    unavailable: 'Niedostępna',
    retry: 'Sprawdź ponownie',
    language: 'Język',
  },
}

export const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages,
})
