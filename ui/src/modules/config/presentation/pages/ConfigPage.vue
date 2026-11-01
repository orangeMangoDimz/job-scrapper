<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { toOptionalNumber, type SiteSetting } from '@/modules/config/domain/entities/ScraperConfig'
import ConfigHistory from '@/modules/config/presentation/components/ConfigHistory.vue'
import FilterFields from '@/modules/config/presentation/components/FilterFields.vue'
import ListInput from '@/modules/config/presentation/components/ListInput.vue'
import SiteSettings from '@/modules/config/presentation/components/SiteSettings.vue'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Skeleton } from '@/shared/components/ui/skeleton'

const SAVED_MESSAGE = 'Config saved'

const store = useConfigStore()
const isStale = computed(() => store.snapshot?.isStale ?? true)
const savedAt = computed(() =>
  store.snapshot === null ? '' : new Date(store.snapshot.updatedAt).toLocaleString(),
)

function updateSite(next: SiteSetting): void {
  if (store.values !== null) {
    store.values.sites = store.values.sites.map((site) => (site.name === next.name ? next : site))
  }
}

async function save(): Promise<void> {
  if (await store.save()) {
    toast.success(SAVED_MESSAGE)
  }
}

onMounted(() => {
  void store.load()
  void store.loadHistory()
})
</script>

<template>
  <div class="flex flex-col gap-6">
    <h1 class="text-title">Config</h1>
    <Skeleton v-if="store.status === 'loading'" class="h-40" />
    <p v-else-if="store.status === 'error'" role="alert">{{ store.errorMessage }}</p>
    <template v-else-if="store.values">
      <form class="flex flex-col gap-4" @submit.prevent="save">
        <p class="text-body-sm text-ink-muted">
          Version {{ store.snapshot?.version }}, saved {{ savedAt }} by
          {{ store.snapshot?.updatedBy }}. Changes apply from the next run
        </p>
        <p v-if="isStale" class="text-body-sm text-ink-muted">
          The scraper is busy, so these values may be out of date. Saving is off until it is free
        </p>
        <fieldset :disabled="isStale" class="flex min-w-0 flex-col gap-4 border-0 p-0">
          <div class="flex flex-col gap-2">
            <Label for="keywords">Keywords, separated by commas</Label>
            <ListInput id="keywords" v-model="store.values.keywords" />
          </div>
          <div class="flex flex-col gap-2">
            <Label for="limit">Limit per site</Label>
            <Input
              id="limit"
              :model-value="store.values.limit ?? ''"
              type="number"
              min="1"
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
              @update:model-value="store.values!.maxAgeHours = toOptionalNumber($event)"
            />
          </div>
          <div class="flex flex-col gap-3">
            <p class="text-body-sm font-semibold">Global filter</p>
            <FilterFields id-prefix="global" v-model="store.values.filter" />
          </div>
          <div class="flex flex-col gap-2">
            <Label for="default-fields">Job fields, separated by commas</Label>
            <ListInput id="default-fields" v-model="store.values.defaultFields" />
          </div>
          <fieldset class="flex flex-col gap-3">
            <legend class="text-body-sm font-semibold">Sites</legend>
            <SiteSettings
              v-for="site in store.values.sites"
              :key="site.name"
              :site="site"
              :default-fields="store.values.defaultFields"
              @update="updateSite"
            />
          </fieldset>
        </fieldset>
        <p v-if="store.saveError" role="alert" class="text-body-sm">{{ store.saveError }}</p>
        <div>
          <Button type="submit" :disabled="store.isSaving || isStale">Save</Button>
        </div>
      </form>
      <ConfigHistory />
    </template>
  </div>
</template>
