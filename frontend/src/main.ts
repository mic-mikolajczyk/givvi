import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'

import App from './App.vue'
import { i18n } from './i18n'
import './style.css'
import StatusView from './views/StatusView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: StatusView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

createApp(App).use(router).use(i18n).mount('#app')
