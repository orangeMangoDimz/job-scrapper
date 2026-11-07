<script setup lang="ts">
import { toJobFieldLabel } from '@/modules/config/domain/entities/ScraperConfig'
import EmptyState from '@/shared/components/EmptyState.vue'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Label } from '@/shared/components/ui/label'

const props = defineProps<{
  idPrefix: string
  legend: string
  modelValue: string[]
  jobFields: string[]
  mandatoryFields: string[]
}>()

const emit = defineEmits<{
  'update:modelValue': [fields: string[]]
}>()

function isLocked(field: string): boolean {
  return props.mandatoryFields.includes(field)
}

function isPicked(field: string): boolean {
  return isLocked(field) || props.modelValue.includes(field)
}

function setField(field: string, isChecked: boolean | 'indeterminate'): void {
  const picked = new Set(props.modelValue)
  if (isChecked === true) {
    picked.add(field)
  } else {
    picked.delete(field)
  }
  emit(
    'update:modelValue',
    props.jobFields.filter((candidate) => picked.has(candidate) && !isLocked(candidate)),
  )
}
</script>

<template>
  <EmptyState
    v-if="jobFields.length === 0"
    compact
    title="No job field list from the scraper."
    hint="Update the scraper to the same version as this page, then reload."
  />
  <fieldset v-else class="min-w-0 border-0 p-0">
    <legend class="sr-only">{{ legend }}</legend>
    <div class="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
      <div v-for="field in jobFields" :key="field" class="flex items-center gap-3">
        <Checkbox
          :id="`${idPrefix}-field-${field}`"
          :model-value="isPicked(field)"
          :disabled="isLocked(field)"
          @update:model-value="setField(field, $event)"
        />
        <Label
          :for="`${idPrefix}-field-${field}`"
          :class="isLocked(field) ? 'text-ink-muted' : 'cursor-pointer'"
        >
          {{ toJobFieldLabel(field) }}
        </Label>
      </div>
    </div>
  </fieldset>
</template>
