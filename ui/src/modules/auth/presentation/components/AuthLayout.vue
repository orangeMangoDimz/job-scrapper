<script setup lang="ts">
import AuthThemeMenu from '@/modules/auth/presentation/components/AuthThemeMenu.vue'
</script>

<template>
  <div class="relative min-h-dvh bg-surface text-ink">
    <header class="absolute top-4 right-4 sm:top-6 sm:right-6">
      <AuthThemeMenu />
    </header>
    <main class="flex min-h-dvh items-center justify-center px-4 py-12 sm:px-8">
      <div data-testid="auth-column" class="flex w-full max-w-110 flex-col gap-6">
        <slot />
      </div>
    </main>
  </div>
</template>
