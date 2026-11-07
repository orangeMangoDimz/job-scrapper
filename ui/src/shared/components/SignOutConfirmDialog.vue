<script setup lang="ts">
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'

defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: []
}>()

function handleOpenChange(value: boolean): void {
  emit('update:open', value)
}

function close(): void {
  emit('update:open', false)
}

function handleConfirm(): void {
  emit('confirm')
  emit('update:open', false)
}
</script>

<template>
  <Dialog :open="open" @update:open="handleOpenChange">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Sign out?</DialogTitle>
        <DialogDescription>You'll need to sign in again to use NoNo Scraper.</DialogDescription>
      </DialogHeader>
      <DialogFooter>
        <Button @click="close">Cancel</Button>
        <Button variant="danger" @click="handleConfirm">Sign out</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
