<script setup lang="ts">
import { computed, ref } from 'vue'
import { CheckIcon, TriangleAlertIcon } from '@lucide/vue'
import { ComboboxInput } from 'reka-ui'
import type { LocationOption } from '@/modules/config/domain/entities/ScraperConfig'
import {
  Combobox,
  ComboboxAnchor,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxItem,
  ComboboxItemIndicator,
  ComboboxViewport,
} from '@/shared/components/ui/combobox'
import {
  TagsInput,
  TagsInputInput,
  TagsInputItem,
  TagsInputItemDelete,
  TagsInputItemText,
} from '@/shared/components/ui/tags-input'

const PLACEHOLDER = 'Pick cities'
const UNKNOWN_HINT = 'Not in the city list'
const NO_MATCH_TEXT = 'No city found'

const props = defineProps<{
  id: string
  modelValue: string[]
  options: LocationOption[]
}>()

const emit = defineEmits<{
  'update:modelValue': [values: string[]]
}>()

const searchTerm = ref('')

const picked = computed({
  get: () => props.modelValue,
  set: (next: string[]) => {
    searchTerm.value = ''
    emit('update:modelValue', next)
  },
})

const labelByValue = computed(
  () => new Map(props.options.map((option) => [option.value, option.label])),
)

const visibleOptions = computed(() => {
  const term = searchTerm.value.trim().toLowerCase()
  return props.options.filter((option) => option.label.toLowerCase().includes(term))
})

function isKnown(value: string): boolean {
  return labelByValue.value.has(value)
}
</script>

<template>
  <Combobox v-model="picked" multiple ignore-filter open-on-focus>
    <ComboboxAnchor as-child>
      <TagsInput
        v-model="picked"
        :delimiter="''"
        :add-on-paste="false"
        :add-on-blur="false"
        :add-on-tab="false"
      >
        <TagsInputItem
          v-for="value in picked"
          :key="value"
          :value="value"
          :data-unknown="isKnown(value) ? undefined : 'true'"
          :title="isKnown(value) ? undefined : UNKNOWN_HINT"
          :class="isKnown(value) ? undefined : 'bg-danger-soft text-danger'"
        >
          <TriangleAlertIcon v-if="!isKnown(value)" class="size-4 shrink-0" aria-hidden="true" />
          <TagsInputItemText>{{ labelByValue.get(value) ?? value }}</TagsInputItemText>
          <TagsInputItemDelete
            :aria-label="`Remove ${labelByValue.get(value) ?? value}${isKnown(value) ? '' : ', not in the city list'}`"
          />
        </TagsInputItem>
        <ComboboxInput v-model="searchTerm" as-child>
          <TagsInputInput
            :id="id"
            :placeholder="picked.length === 0 ? PLACEHOLDER : ''"
            @keydown.enter.prevent
          />
        </ComboboxInput>
      </TagsInput>
    </ComboboxAnchor>
    <ComboboxContent>
      <ComboboxViewport>
        <ComboboxEmpty>{{ NO_MATCH_TEXT }}</ComboboxEmpty>
        <ComboboxItem v-for="option in visibleOptions" :key="option.value" :value="option.value">
          <span class="truncate">{{ option.label }}</span>
          <ComboboxItemIndicator>
            <CheckIcon />
          </ComboboxItemIndicator>
        </ComboboxItem>
      </ComboboxViewport>
    </ComboboxContent>
  </Combobox>
</template>
