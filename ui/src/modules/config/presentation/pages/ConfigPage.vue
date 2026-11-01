<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { isLocked, toOptionalNumber } from '@/modules/config/domain/entities/ScraperConfig'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import { Button } from '@/shared/components/ui/button'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Skeleton } from '@/shared/components/ui/skeleton'
import { parseKeywords } from '@/shared/utils/parseKeywords'

const SAVED_MESSAGE = 'Config saved'

const store = useConfigStore()
const isReadOnly = computed(() => store.snapshot?.isReadOnly ?? true)
const locked = computed(() => store.snapshot?.locked ?? [])

const keywordText = computed({
  get: () => store.values?.keywords.join(', ') ?? '',
  set: (text: string) => {
    if (store.values !== null) {
      store.values.keywords = parseKeywords(text)
    }
  },
})

const proxyText = computed({
  get: () => store.values?.proxyUrl ?? '',
  set: (text: string) => {
    if (store.values !== null) {
      store.values.proxyUrl = text.trim() === '' ? null : text.trim()
    }
  },
})

function isFieldDisabled(path: string): boolean {
  return isReadOnly.value || isLocked(locked.value, path)
}

async function save(): Promise<void> {
  if (await store.save()) {
    toast.success(SAVED_MESSAGE)
  }
}

onMounted(() => void store.load())
</script>

<template>
  <div class="flex flex-col gap-6">
    <h1 class="text-title">Config</h1>
    <Skeleton v-if="store.status === 'loading'" class="h-40" />
    <p v-else-if="store.status === 'error'" role="alert">{{ store.errorMessage }}</p>
    <form v-else-if="store.values" class="flex flex-col gap-4" @submit.prevent="save">
      <p v-if="isReadOnly" class="text-body-sm text-ink-muted">
        Read-only here. Change config through git and deploy
      </p>
      <p v-if="locked.length > 0" class="text-body-sm text-ink-muted">
        Disabled fields are set by config.dev.patch.yaml
      </p>
      <p v-if="store.snapshot?.isStale" class="text-body-sm text-ink-muted">
        The scraper is busy, so these values may be out of date
      </p>
      <div class="flex flex-col gap-2">
        <Label for="keywords">Keywords, separated by commas</Label>
        <Input id="keywords" v-model="keywordText" :disabled="isFieldDisabled('keywords')" />
      </div>
      <div class="flex flex-col gap-2">
        <Label for="limit">Limit per site</Label>
        <Input
          id="limit"
          :model-value="store.values.limit ?? ''"
          type="number"
          min="1"
          :disabled="isFieldDisabled('limit')"
          @update:model-value="store.values!.limit = toOptionalNumber($event)"
        />
      </div>
      <div class="flex flex-col gap-2">
        <Label for="max-age">Max job age in hours</Label>
        <Input
          id="max-age"
          :model-value="store.values.maxAgeHours ?? ''"
          type="number"
          min="1"
          :disabled="isFieldDisabled('max_age_hours')"
          @update:model-value="store.values!.maxAgeHours = toOptionalNumber($event)"
        />
      </div>
      <div class="flex flex-col gap-2">
        <Label for="proxy">Proxy URL</Label>
        <Input id="proxy" v-model="proxyText" :disabled="isFieldDisabled('proxy')" />
      </div>
      <fieldset class="flex flex-col gap-3">
        <legend class="text-body-sm font-semibold">Sites</legend>
        <div v-for="site in store.values.sites" :key="site.name" class="flex items-center gap-3">
          <Checkbox
            :id="`config-site-${site.name}`"
            :model-value="site.isEnabled"
            :disabled="isFieldDisabled(`sites.${site.name}.enabled`)"
            @update:model-value="site.isEnabled = $event === true"
          />
          <Label :for="`config-site-${site.name}`" class="w-28">{{ site.name }}</Label>
          <Input
            :model-value="site.limit ?? ''"
            type="number"
            min="1"
            class="w-24"
            :aria-label="`${site.name} limit`"
            :disabled="isFieldDisabled(`sites.${site.name}.limit`)"
            @update:model-value="site.limit = toOptionalNumber($event)"
          />
        </div>
      </fieldset>
      <p v-if="store.saveError" role="alert" class="text-body-sm">{{ store.saveError }}</p>
      <div v-if="!isReadOnly">
        <Button type="submit" :disabled="store.isSaving">Save</Button>
      </div>
    </form>
  </div>
</template>
