<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { toOptionalNumber, type SiteSetting } from '@/modules/config/domain/entities/ScraperConfig'
import ConfigHistory from '@/modules/config/presentation/components/ConfigHistory.vue'
import FilterFields from '@/modules/config/presentation/components/FilterFields.vue'
import ListInput from '@/modules/config/presentation/components/ListInput.vue'
import SiteSettings from '@/modules/config/presentation/components/SiteSettings.vue'
import { useConfigStore } from '@/modules/config/presentation/stores/useConfigStore'
import OutlineNav from '@/shared/components/OutlineNav.vue'
import PageLoadState from '@/shared/components/PageLoadState.vue'
import PageSection from '@/shared/components/PageSection.vue'
import type { OutlineItem } from '@/shared/components/types'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Skeleton } from '@/shared/components/ui/skeleton'

const SAVED_MESSAGE = 'Config saved'
const OUTLINE_KEY_ATTRIBUTE = 'data-outline-key'
const OUTLINE: OutlineItem[] = [
  { key: 'general', label: 'General', badge: null, entries: [] },
  { key: 'filter', label: 'Global filter', badge: null, entries: [] },
  { key: 'fields', label: 'Job fields', badge: null, entries: [] },
  { key: 'sites', label: 'Sites', badge: null, entries: [] },
  { key: 'history', label: 'Older versions', badge: null, entries: [] },
]

const store = useConfigStore()
const isStale = computed(() => store.snapshot?.isStale ?? true)
const isLoading = computed(() => store.status === 'idle' || store.status === 'loading')
const enabledSiteCount = computed(
  () => store.values?.sites.filter((site) => site.isEnabled).length ?? 0,
)
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
  <header class="flex flex-wrap items-start justify-between gap-3">
    <div class="flex min-w-0 flex-col gap-1">
      <h1 class="text-title text-ink">Config</h1>
      <p v-if="store.snapshot" class="text-body-sm text-ink-muted">
        Version {{ store.snapshot.version }}, saved {{ savedAt }} by {{ store.snapshot.updatedBy }}.
        Changes apply from the next run
      </p>
    </div>
  </header>

  <PageLoadState
    v-if="isLoading || store.status === 'error'"
    :is-error="store.status === 'error'"
    loading-label="Loading config"
    error-title="Could not load config"
    :error-message="store.errorMessage"
    @retry="store.load"
  >
    <div class="flex flex-col gap-6 md:gap-4 xl:grid xl:grid-cols-[minmax(0,1fr)_16rem] xl:gap-6">
      <div class="flex flex-col gap-6 md:gap-4">
        <Skeleton v-for="index in 3" :key="index" class="h-48 w-full rounded-lg" />
      </div>
      <Skeleton class="h-64 w-full rounded-lg max-xl:hidden" />
    </div>
  </PageLoadState>

  <div
    v-else-if="store.values"
    class="flex flex-col gap-6 md:gap-4 xl:grid xl:grid-cols-[minmax(0,1fr)_16rem] xl:items-start xl:gap-6"
  >
    <div class="flex min-w-0 flex-col gap-6 md:gap-4">
      <p
        v-if="isStale"
        role="status"
        class="rounded-md border border-line-strong p-4 text-body-sm text-ink"
      >
        The scraper is busy, so these values may be out of date. Saving is off until it is free
      </p>

      <form class="flex flex-col gap-6 md:gap-4" @submit.prevent="save">
        <fieldset :disabled="isStale" class="flex min-w-0 flex-col gap-6 border-0 p-0 md:gap-4">
          <PageSection
            :[OUTLINE_KEY_ATTRIBUTE]="'general'"
            title="General"
            description="What to search for and how much to keep"
          >
            <div class="flex flex-col gap-4">
              <div class="flex flex-col gap-2">
                <Label for="keywords">Keywords, separated by commas</Label>
                <ListInput id="keywords" v-model="store.values.keywords" />
              </div>
              <div class="grid gap-4 sm:grid-cols-2">
                <div class="flex flex-col gap-2">
                  <Label for="limit">Limit per site</Label>
                  <Input
                    id="limit"
                    :model-value="store.values.limit ?? ''"
                    type="number"
                    required
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
                    :required="store.snapshot?.values.maxAgeHours !== null"
                    min="1"
                    @update:model-value="store.values!.maxAgeHours = toOptionalNumber($event)"
                  />
                </div>
              </div>
            </div>
          </PageSection>

          <PageSection
            :[OUTLINE_KEY_ATTRIBUTE]="'filter'"
            title="Global filter"
            description="Applies to every site that has no filter of its own"
          >
            <FilterFields id-prefix="global" v-model="store.values.filter" />
          </PageSection>

          <PageSection
            :[OUTLINE_KEY_ATTRIBUTE]="'fields'"
            title="Job fields"
            description="Fields saved for each job"
          >
            <div class="flex flex-col gap-2">
              <Label for="default-fields">Job fields, separated by commas</Label>
              <ListInput id="default-fields" v-model="store.values.defaultFields" />
            </div>
          </PageSection>

          <PageSection
            :[OUTLINE_KEY_ATTRIBUTE]="'sites'"
            title="Sites"
            :description="`${enabledSiteCount} of ${store.values.sites.length} turned on`"
          >
            <div class="flex flex-col gap-4 md:gap-3">
              <SiteSettings
                v-for="site in store.values.sites"
                :key="site.name"
                :site="site"
                :default-fields="store.values.defaultFields"
                @update="updateSite"
              />
            </div>
          </PageSection>
        </fieldset>

        <ConfigHistory :[OUTLINE_KEY_ATTRIBUTE]="'history'" />

        <div
          data-slot="save-bar"
          class="sticky bottom-0 z-20 -mx-4 flex flex-wrap items-center justify-end gap-3 border-t border-line bg-surface px-4 py-3 md:mx-0 md:rounded-lg md:border"
        >
          <p v-if="store.saveError" role="alert" class="mr-auto text-body-sm text-danger">
            {{ store.saveError }}
          </p>
          <Button type="submit" variant="primary" :disabled="store.isSaving || isStale">
            {{ store.isSaving ? 'Saving' : 'Save' }}
          </Button>
        </div>
      </form>
    </div>

    <OutlineNav
      :items="OUTLINE"
      label="Config outline"
      :key-attribute="OUTLINE_KEY_ATTRIBUTE"
      scroll-block="start"
      class="max-xl:hidden xl:sticky xl:top-8 xl:max-h-[calc(100dvh-4rem)]"
    />
  </div>
</template>
