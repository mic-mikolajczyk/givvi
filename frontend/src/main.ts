import { createApp, nextTick, watch } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import App from './App.vue'
import { ApiError, refreshUser, safeReturnTo } from './api'
import { i18n } from './i18n'
import './style.css'
import StatusView from './views/StatusView.vue'
import AccountShell from './views/AccountShell.vue'
import AuthView from './views/AuthView.vue'
import EventDetailView from './views/EventDetailView.vue'
import EventsView from './views/EventsView.vue'
import InvitationView from './views/InvitationView.vue'
import ProfileView from './views/ProfileView.vue'
import WishlistView from './views/WishlistView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/events' },
    { path: '/status', component: StatusView },
    ...['login', 'register', 'verify', 'forgot-password', 'reset-password'].map((name) => ({ path: `/${name}`, name, component: AuthView })),
    { path: '/invite/:eventId', name: 'invite', component: InvitationView },
    {
      path: '/', component: AccountShell, meta: { authenticated: true }, children: [
        { path: 'events', name: 'events', component: EventsView },
        { path: 'events/:eventId', name: 'event', component: EventDetailView },
        { path: 'events/:eventId/participants/:participantId/wishlist', name: 'participant-wishlist', component: WishlistView },
        { path: 'wishlist', name: 'wishlist', component: WishlistView },
        { path: 'profile', name: 'profile', component: ProfileView },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

const storedLanguage = localStorage.getItem('givvi-language')
if (storedLanguage === 'en' || storedLanguage === 'pl') i18n.global.locale.value = storedLanguage
watch(i18n.global.locale, (language) => { document.documentElement.lang = language }, { immediate: true })

router.beforeEach(async (destination) => {
  if (destination.meta.authenticated) {
    try {
      const user = await refreshUser()
      i18n.global.locale.value = user.language
    } catch (failure) {
      return { path: '/login', query: { next: safeReturnTo(destination.fullPath), ...(failure instanceof ApiError && failure.code !== 'unauthenticated' ? { error: failure.code } : {}) } }
    }
  }
})
router.afterEach(async () => {
  await nextTick()
  document.querySelector<HTMLElement>('main h1')?.focus()
})

createApp(App).use(router).use(i18n).mount('#app')
