<template>
  <div class="flex min-h-svh flex-col bg-surface">
    <slot name="header" />
    <main class="flex-1 px-4 pt-4 pb-12 md:px-12 md:pt-8 md:pb-16">
      <div class="mx-auto flex w-full max-w-content flex-col gap-6">
        <slot />
      </div>
    </main>
  </div>
</template>
