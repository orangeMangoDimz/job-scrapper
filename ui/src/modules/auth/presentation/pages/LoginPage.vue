<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import AuthLayout from '@/modules/auth/presentation/components/AuthLayout.vue'
import { useAuthStore } from '@/modules/auth/presentation/stores/useAuthStore'
import PasswordInput from '@/shared/components/PasswordInput.vue'
import { Button } from '@/shared/components/ui/button'

const auth = useAuthStore()
const router = useRouter()
const password = ref('')
const isSubmitting = ref(false)

async function submit(): Promise<void> {
  isSubmitting.value = true
  const isDone = await auth.login(password.value)
  isSubmitting.value = false
  if (isDone) {
    await router.push('/')
  }
}
</script>

<template>
  <AuthLayout>
    <h1 class="text-center text-display text-ink">Sign in to NoNo Scraper</h1>
    <form class="flex flex-col gap-4" :aria-busy="isSubmitting" @submit.prevent="submit">
      <PasswordInput
        v-model="password"
        label="Password"
        autocomplete="current-password"
        required
        :is-invalid="auth.errorMessage !== null"
      />
      <p v-if="auth.errorMessage" role="alert" class="text-body-sm text-danger">
        {{ auth.errorMessage }}
      </p>
      <Button type="submit" variant="primary" :disabled="password === '' || isSubmitting">
        Sign in
      </Button>
    </form>
  </AuthLayout>
</template>
