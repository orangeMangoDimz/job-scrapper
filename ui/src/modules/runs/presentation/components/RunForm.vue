<script setup lang="ts">
import { Play } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import type { RunOptions } from '@/modules/runs/domain/entities/Run'
import { Button } from '@/shared/components/ui/button'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { parseKeywords } from '@/shared/utils/parseKeywords'

const props = defineProps<{ options: RunOptions; isRunning: boolean }>()
const emit = defineEmits<{ start: [keywords: string[], sites: string[]] }>()

const keywordText = ref('')
const pickedSites = ref<string[]>([])

const keywords = computed(() => parseKeywords(keywordText.value))
const canStart = computed(
  () => keywords.value.length > 0 && pickedSites.value.length > 0 && !props.isRunning,
)

watch(
  () => props.options,
  (options) => {
    pickedSites.value = options.sites.filter((site) => site.isEnabled).map((site) => site.name)
  },
  { immediate: true },
)

function setSite(name: string, isPicked: boolean | 'indeterminate'): void {
  pickedSites.value =
    isPicked === true
      ? [...pickedSites.value, name]
      : pickedSites.value.filter((site) => site !== name)
}
</script>

<template>
  <form class="flex flex-col gap-4" @submit.prevent="emit('start', keywords, pickedSites)">
    <div class="flex flex-col gap-2">
      <Label for="run-keywords">Keywords, separated by commas</Label>
      <div class="flex flex-col gap-3 sm:flex-row">
        <Input
          id="run-keywords"
          v-model="keywordText"
          placeholder="data analyst, python"
          class="sm:flex-1"
        />
        <Button type="submit" variant="primary" :disabled="!canStart">
          <Play aria-hidden="true" />
          {{ isRunning ? 'Scrape running' : 'Run scrape' }}
        </Button>
      </div>
    </div>
    <fieldset class="flex flex-col gap-2">
      <legend class="mb-2 text-body-sm font-semibold text-ink">Sites</legend>
      <div class="flex flex-wrap gap-x-6 gap-y-3">
        <div v-for="site in options.sites" :key="site.name" class="flex items-center gap-3">
          <Checkbox
            :id="`site-${site.name}`"
            :model-value="pickedSites.includes(site.name)"
            @update:model-value="setSite(site.name, $event)"
          />
          <Label :for="`site-${site.name}`" class="cursor-pointer">{{ site.name }}</Label>
        </div>
      </div>
    </fieldset>
  </form>
</template>
