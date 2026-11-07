<script setup lang="ts">
import {
  EMPTY_FILTER,
  toDelaySeconds,
  toOptionalNumber,
  type ApiSetting,
  type SiteChanges,
  type SiteSetting,
} from '@/modules/config/domain/entities/ScraperConfig'
import FilterFields from '@/modules/config/presentation/components/FilterFields.vue'
import LineListInput from '@/modules/config/presentation/components/LineListInput.vue'
import JobFieldsInput from '@/modules/config/presentation/components/JobFieldsInput.vue'
import { Checkbox } from '@/shared/components/ui/checkbox'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

const GLOBAL_VALUE_HINT = 'Global'

const props = defineProps<{
  site: SiteSetting
  defaultFields: string[]
  jobFields: string[]
  mandatoryFields: string[]
}>()

const emit = defineEmits<{
  update: [site: SiteSetting]
}>()

function change(changes: SiteChanges): void {
  emit('update', { ...props.site, ...changes })
}

function changeApi(changes: Partial<ApiSetting>): void {
  if (props.site.api !== null) {
    change({ api: { ...props.site.api, ...changes } })
  }
}

function changeDelayMin(value: string | number): void {
  const max = props.site.api?.delaySeconds?.[1] ?? null
  changeApi({ delaySeconds: toDelaySeconds(toOptionalNumber(value), max) })
}

function changeDelayMax(value: string | number): void {
  const min = props.site.api?.delaySeconds?.[0] ?? null
  changeApi({ delaySeconds: toDelaySeconds(min, toOptionalNumber(value)) })
}
</script>

<template>
  <div class="flex flex-col gap-2 rounded-md border border-line p-4">
    <div class="flex items-center gap-3">
      <Checkbox
        :id="`config-site-${site.name}`"
        :model-value="site.isEnabled"
        @update:model-value="change({ isEnabled: $event === true })"
      />
      <Label :for="`config-site-${site.name}`" class="w-28">{{ site.name }}</Label>
      <Input
        :model-value="site.limit ?? ''"
        type="number"
        min="1"
        class="w-24"
        :aria-label="`${site.name} limit`"
        :placeholder="GLOBAL_VALUE_HINT"
        @update:model-value="change({ limit: toOptionalNumber($event) })"
      />
    </div>
    <details>
      <summary class="cursor-pointer text-body-sm text-ink-muted">More settings</summary>
      <div class="mt-3 flex flex-col gap-4">
        <div class="flex flex-col gap-2">
          <Label :for="`${site.name}-max-age`">Max job age in hours</Label>
          <Input
            :id="`${site.name}-max-age`"
            :model-value="site.maxAgeHours ?? ''"
            type="number"
            min="1"
            :placeholder="GLOBAL_VALUE_HINT"
            @update:model-value="change({ maxAgeHours: toOptionalNumber($event) })"
          />
        </div>
        <div class="flex flex-col gap-3">
          <div class="flex items-center gap-3">
            <Checkbox
              :id="`${site.name}-own-filter`"
              :model-value="site.filter !== null"
              @update:model-value="change({ filter: $event === true ? EMPTY_FILTER : null })"
            />
            <Label :for="`${site.name}-own-filter`">
              Use its own filter. Leave the fields empty for no filter
            </Label>
          </div>
          <FilterFields
            v-if="site.filter !== null"
            :id-prefix="site.name"
            :model-value="site.filter"
            @update:model-value="change({ filter: $event })"
          />
        </div>
        <div class="flex flex-col gap-3">
          <div class="flex items-center gap-3">
            <Checkbox
              :id="`${site.name}-own-fields`"
              :model-value="site.fields !== null"
              @update:model-value="change({ fields: $event === true ? defaultFields : null })"
            />
            <Label :for="`${site.name}-own-fields`">Use its own job fields</Label>
          </div>
          <JobFieldsInput
            v-if="site.fields !== null"
            :id-prefix="site.name"
            :legend="`${site.name} job fields`"
            :model-value="site.fields"
            :job-fields="jobFields"
            :mandatory-fields="mandatoryFields"
            @update:model-value="change({ fields: $event })"
          />
        </div>
        <div v-if="site.api !== null" class="flex flex-col gap-3">
          <div class="flex items-center gap-3">
            <Checkbox
              :id="`${site.name}-api-enabled`"
              :model-value="site.api.isEnabled"
              @update:model-value="changeApi({ isEnabled: $event === true })"
            />
            <Label :for="`${site.name}-api-enabled`">Use the API</Label>
          </div>
          <div class="flex items-center gap-3">
            <Checkbox
              :id="`${site.name}-api-country`"
              :model-value="site.api.isCountryWide"
              @update:model-value="changeApi({ isCountryWide: $event === true })"
            />
            <Label :for="`${site.name}-api-country`">Also search the whole country</Label>
          </div>
          <div class="flex flex-col gap-2">
            <Label :for="`${site.name}-api-locations`">API locations, one per line</Label>
            <LineListInput
              :id="`${site.name}-api-locations`"
              :model-value="site.api.locations"
              @update:model-value="changeApi({ locations: $event })"
            />
          </div>
          <div class="flex items-center gap-3">
            <Label :for="`${site.name}-api-delay-min`">Delay in seconds, min and max</Label>
            <Input
              :id="`${site.name}-api-delay-min`"
              :model-value="site.api.delaySeconds?.[0] ?? ''"
              type="number"
              min="0"
              step="0.5"
              class="w-24"
              @update:model-value="changeDelayMin"
            />
            <Input
              :model-value="site.api.delaySeconds?.[1] ?? ''"
              type="number"
              min="0"
              step="0.5"
              class="w-24"
              :aria-label="`${site.name} max delay`"
              @update:model-value="changeDelayMax"
            />
          </div>
        </div>
      </div>
    </details>
  </div>
</template>
