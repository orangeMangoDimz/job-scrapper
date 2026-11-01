<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'
import { Button } from '@/shared/components/ui/button'
import { Toaster } from '@/shared/components/ui/sonner'

const NAV_ITEMS = [
  { to: '/runs', label: 'Runs' },
  { to: '/config', label: 'Config' },
]

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const showsNav = computed(() => route.meta.isPublic !== true)

async function signOut(): Promise<void> {
  await auth.logout()
  await router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-surface text-ink">
    <header v-if="showsNav" class="border-b border-line">
      <div class="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
        <span class="text-subheading">Scraper</span>
        <nav aria-label="Main navigation" class="flex gap-4">
          <RouterLink
            v-for="item in NAV_ITEMS"
            :key="item.to"
            :to="item.to"
            class="text-body-sm text-ink-muted"
            active-class="text-ink"
          >
            {{ item.label }}
          </RouterLink>
        </nav>
        <Button v-if="auth.isAuthRequired" class="ml-auto" variant="ink" @click="signOut">
          Sign out
        </Button>
      </div>
    </header>
    <main class="mx-auto max-w-5xl px-4 py-6">
      <RouterView />
    </main>
    <Toaster />
  </div>
</template>
