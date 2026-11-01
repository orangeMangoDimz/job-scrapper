<script setup lang="ts">
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
    keywordText.value = options.keywords.join(', ')
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
      <Label for="keywords">Keywords, separated by commas</Label>
      <Input id="keywords" v-model="keywordText" />
    </div>
    <fieldset class="flex flex-col gap-2">
      <legend class="text-body-sm font-semibold">Sites</legend>
      <div class="flex flex-wrap gap-4">
        <div v-for="site in options.sites" :key="site.name" class="flex items-center gap-2">
          <Checkbox
            :id="`site-${site.name}`"
            :model-value="pickedSites.includes(site.name)"
            @update:model-value="setSite(site.name, $event)"
          />
          <Label :for="`site-${site.name}`">{{ site.name }}</Label>
        </div>
      </div>
    </fieldset>
    <div>
      <Button type="submit" :disabled="!canStart">
        {{ isRunning ? 'Scrape running' : 'Run scrape' }}
      </Button>
    </div>
  </form>
</template>
