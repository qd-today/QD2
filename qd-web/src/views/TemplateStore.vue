<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import api from '@/api'

const message = useMessage()
const dialog = useDialog()

const sources = ref<any[]>([])
const activeSource = ref<number | null>(null)
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 30
const search = ref('')
const loading = ref(false)
const syncing = ref(false)
const installing = ref<string | null>(null)
const pageError = ref('')

const showAddSource = ref(false)
const newSource = ref({
  name: 'qd-today 官方模板库',
  url: 'https://raw.githubusercontent.com/qd-today/templates/master/tpls_history.json',
})

async function loadSources() {
  loading.value = true
  pageError.value = ''
  try {
    const res = await api.get('/api/template-sources')
    sources.value = res.data
    if (sources.value.length > 0 && activeSource.value === null) {
      activeSource.value = sources.value[0].id
      await browse()
    }
  } catch (e: any) {
    pageError.value = e.response?.data?.detail || '模板库加载失败，请稍后重试'
    message.error(pageError.value)
  } finally {
    loading.value = false
  }
}

async function addSource() {
  try {
    const res = await api.post('/api/template-sources', newSource.value)
    showAddSource.value = false
    message.success('订阅成功，开始同步…')
    activeSource.value = res.data.id
    await loadSources()
    await sync()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '订阅失败')
  }
}

async function removeSource(id: number) {
  dialog.warning({
    title: '取消订阅',
    content: '确定取消订阅该模板源？已安装的模板不受影响。',
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      await api.delete(`/api/template-sources/${id}`)
      if (activeSource.value === id) {
        activeSource.value = null
        items.value = []
        total.value = 0
      }
      await loadSources()
      message.success('已取消订阅')
    },
  })
}

async function sync() {
  if (!activeSource.value) return
  syncing.value = true
  try {
    const res = await api.post(`/api/template-sources/${activeSource.value}/sync`)
    message.success(`同步完成: ${res.data.template_count} 个模板 (版本 ${res.data.manifest_version})`)
    await loadSources()
    await browse()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '同步失败')
  } finally {
    syncing.value = false
  }
}

async function browse() {
  if (!activeSource.value) return
  loading.value = true
  pageError.value = ''
  try {
    const res = await api.get(`/api/template-sources/${activeSource.value}/templates`, {
      params: { search: search.value || undefined, page: page.value, page_size: pageSize },
    })
    items.value = res.data.items
    total.value = res.data.total
  } catch (e: any) {
    pageError.value = e.response?.data?.detail || '模板列表加载失败，请稍后重试'
    message.error(pageError.value)
  } finally {
    loading.value = false
  }
}

async function install(name: string) {
  if (!activeSource.value) return
  installing.value = name
  try {
    const res = await api.post(
      `/api/template-sources/${activeSource.value}/install/${encodeURIComponent(name)}`
    )
    message.success(`已安装「${res.data.name}」(${res.data.requests} 个请求)`)
    await browse()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '安装失败')
  } finally {
    installing.value = null
  }
}

function doSearch() {
  page.value = 1
  browse()
}

onMounted(loadSources)
</script>

<template>
  <div>
    <n-alert v-if="pageError" type="error" title="模板库暂时不可用" class="mb-4">
      <div class="flex items-center justify-between gap-3">
        <span>{{ pageError }}</span>
        <n-button size="small" @click="loadSources">重试</n-button>
      </div>
    </n-alert>
    <div class="flex flex-wrap items-center gap-3 mb-4">
      <n-select
        v-model:value="activeSource"
        :options="sources.map((s) => ({ label: `${s.name} (${s.template_count})`, value: s.id }))"
        placeholder="选择模板源"
        class="w-64"
        @update:value="browse"
      />
      <n-button :loading="syncing" @click="sync">同步</n-button>
      <n-button type="primary" @click="showAddSource = true">订阅新源</n-button>
      <n-button
        v-if="activeSource"
        quaternary
        type="error"
        @click="removeSource(activeSource!)"
      >
        取消订阅
      </n-button>
      <div class="flex-1" />
      <n-input-group class="!w-72">
        <n-input v-model:value="search" placeholder="搜索名称/作者/说明" @keyup.enter="doSearch" />
        <n-button type="primary" ghost @click="doSearch">搜索</n-button>
      </n-input-group>
    </div>

    <n-empty
      v-if="sources.length === 0"
      description="尚未订阅任何模板源，点击「订阅新源」开始（默认为 qd-today 官方模板库）"
      class="mt-16"
    />

    <n-spin :show="loading">
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        <n-card v-for="it in items" :key="it.name" size="small" class="rounded-lg" hoverable>
          <div class="flex justify-between items-start gap-2">
            <div class="min-w-0">
              <div class="font-medium truncate" :title="it.name">{{ it.name }}</div>
              <div class="text-xs text-gray-400 mt-0.5">{{ it.author || '匿名' }}</div>
              <div
                class="text-xs text-gray-500 mt-1 line-clamp-2"
                v-html="(it.comments || '').replace(/<br\s*\/?>/g, ' ')"
              />
            </div>
            <n-button
              size="small"
              :type="it.installed ? 'default' : 'primary'"
              :disabled="it.installed"
              :loading="installing === it.name"
              @click="install(it.name)"
            >
              {{ it.installed ? '已安装' : '安装' }}
            </n-button>
          </div>
        </n-card>
      </div>
    </n-spin>

    <div class="flex justify-center mt-4">
      <n-pagination
        v-model:page="page"
        :item-count="total"
        :page-size="pageSize"
        @update:page="browse"
      />
    </div>

    <n-modal v-model:show="showAddSource" preset="dialog" title="订阅模板源">
      <n-form>
        <n-form-item label="名称">
          <n-input v-model:value="newSource.name" />
        </n-form-item>
        <n-form-item label="Manifest URL (tpls_history.json)">
          <n-input v-model:value="newSource.url" />
        </n-form-item>
      </n-form>
      <template #action>
        <n-button @click="showAddSource = false">取消</n-button>
        <n-button type="primary" @click="addSource">订阅</n-button>
      </template>
    </n-modal>
  </div>
</template>
