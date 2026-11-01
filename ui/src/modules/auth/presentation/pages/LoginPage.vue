<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

const auth = useAuthStore()
const router = useRouter()
const password = ref('')
const isSubmitting = ref(false)

async function submit(): Promise<void> {
  isSubmitting.value = true
  const isDone = await auth.login(password.value)
  isSubmitting.value = false
  if (isDone) {
    await router.push('/runs')
  }
}
</script>

<template>
  <section class="mx-auto mt-24 max-w-sm">
    <h1 class="text-title">Scraper</h1>
    <form class="mt-6 flex flex-col gap-4" @submit.prevent="submit">
      <div class="flex flex-col gap-2">
        <Label for="password">Password</Label>
        <Input id="password" v-model="password" type="password" autocomplete="current-password" />
      </div>
      <p v-if="auth.errorMessage" role="alert" class="text-body-sm">{{ auth.errorMessage }}</p>
      <Button type="submit" :disabled="password === '' || isSubmitting">Sign in</Button>
    </form>
  </section>
</template>
