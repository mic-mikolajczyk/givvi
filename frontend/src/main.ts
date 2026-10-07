import { createApp, nextTick, watch } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import App from './App.vue'
import { ApiError, refreshUser, safeReturnTo } from './api'
import { i18n } from './i18n'
import './style.css'
import StatusView from './views/StatusView.vue'
import AccountShell from './views/AccountShell.vue'
import AuthView from './views/AuthView.vue'
import DashboardView from './views/DashboardView.vue'
import ProfileView from './views/ProfileView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/events' },
    { path: '/status', component: StatusView },
    ...['login', 'register', 'verify', 'forgot-password', 'reset-password'].map((name) => ({ path: `/${name}`, name, component: AuthView })),
    {
      path: '/', component: AccountShell, meta: { authenticated: true }, children: [
        { path: 'events', name: 'events', component: DashboardView },
        { path: 'wishlist', name: 'wishlist', component: DashboardView },
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
