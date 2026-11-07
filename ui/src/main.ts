import { createApp } from 'vue'
import { createPinia } from 'pinia'

import '@/shared/styles/main.css'

import App from './App.vue'
import router from './router'
import { useThemeStore } from '@/shared/stores/useThemeStore'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
useThemeStore(pinia).init()
app.use(router)
app.mount('#app')
