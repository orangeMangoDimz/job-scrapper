<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'
import { navItems } from '@/router/navigation'
import AppHeader from '@/shared/components/AppHeader.vue'
import AppShell from '@/shared/components/AppShell.vue'
import SelectionTransition from '@/shared/components/SelectionTransition.vue'
import { Toaster } from '@/shared/components/ui/sonner'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const isPublicPage = computed(() => route.meta.isPublic === true)

async function signOut(): Promise<void> {
  await auth.logout()
  await router.push('/login')
}
</script>

<template>
  <RouterView v-if="isPublicPage" />
  <AppShell v-else>
    <template #header>
      <AppHeader :items="navItems" :can-sign-out="auth.isAuthRequired" @sign-out="signOut" />
    </template>
    <RouterView v-slot="{ Component, route: current }">
      <SelectionTransition>
        <component :is="Component" :key="current.matched[0]?.path" />
      </SelectionTransition>
    </RouterView>
  </AppShell>
  <Toaster />
</template>
