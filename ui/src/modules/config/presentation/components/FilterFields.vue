<script setup lang="ts">
import type { FilterSetting } from '@/modules/config/domain/entities/ScraperConfig'
import ListInput from '@/modules/config/presentation/components/ListInput.vue'
import { Label } from '@/shared/components/ui/label'

const props = defineProps<{
  idPrefix: string
  modelValue: FilterSetting
}>()

const emit = defineEmits<{
  'update:modelValue': [filter: FilterSetting]
}>()

function change(changes: Partial<FilterSetting>): void {
  emit('update:modelValue', { ...props.modelValue, ...changes })
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <div class="flex flex-col gap-2">
      <Label :for="`${idPrefix}-location`">Locations, separated by commas</Label>
      <ListInput
        :id="`${idPrefix}-location`"
        :model-value="modelValue.location"
        @update:model-value="change({ location: $event })"
      />
    </div>
    <div class="flex flex-col gap-2">
      <Label :for="`${idPrefix}-employment`">Employment types, separated by commas</Label>
      <ListInput
        :id="`${idPrefix}-employment`"
        :model-value="modelValue.employmentType"
        @update:model-value="change({ employmentType: $event })"
      />
    </div>
    <div class="flex flex-col gap-2">
      <Label :for="`${idPrefix}-work`">Work types, separated by commas</Label>
      <ListInput
        :id="`${idPrefix}-work`"
        :model-value="modelValue.workType"
        @update:model-value="change({ workType: $event })"
      />
    </div>
  </div>
</template>
