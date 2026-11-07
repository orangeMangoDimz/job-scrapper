<script setup lang="ts">
import { SidebarInset, SidebarProvider, SidebarTrigger } from '@/shared/components/ui/sidebar'
</script>

<template>
  <SidebarProvider>
    <slot name="sidebar" />
    <div class="flex min-w-0 flex-1 flex-col">
      <div
        class="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-2 border-b border-line bg-surface px-4 md:hidden"
      >
        <SidebarTrigger class="size-11" />
        <span class="text-subheading font-bold text-ink">NoNo Scraper</span>
      </div>
      <SidebarInset class="px-4 pt-4 pb-12 md:px-12 md:pt-8 md:pb-16">
        <div class="mx-auto flex w-full max-w-content flex-1 flex-col gap-6">
          <slot />
        </div>
      </SidebarInset>
    </div>
  </SidebarProvider>
</template>
