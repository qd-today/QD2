<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import api from '@/api'

const message = useMessage()
const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const search = ref('')
const loading = ref(false)
const installingId = ref<number | null>(null)

async function loadTemplates() {
  loading.value = true
  try {
    const response = await api.get('/api/templates/published', {
      params: {
        page: page.value,
        page_size: pageSize.value,
        search: search.value.trim() || undefined,
      },
    })
    items.value = response.data.items
    total.value = response.data.total
  } catch (error: any) {
    message.error(error.response?.data?.detail || '已发布模板加载失败')
  } finally {
    loading.value = false
  }
}

async function doSearch() {
  page.value = 1
  await loadTemplates()
}

async function handlePageChange(nextPage: number) {
  page.value = nextPage
  await loadTemplates()
}

async function handlePageSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
  await loadTemplates()
}

async function installTemplate(row: any) {
  installingId.value = row.id
  try {
    await api.post(`/api/templates/published/${row.id}/install`)
    row.installed = true
    message.success(`已安装「${row.name}」`)
  } catch (error: any) {
    message.error(error.response?.data?.detail || '模板安装失败')
  } finally {
    installingId.value = null
  }
}

function formatDateTime(value?: string | null) {
  if (!value) return '-'
  const normalized = value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString()
}

onMounted(loadTemplates)
</script>

<template>
  <div>
    <div class="flex flex-wrap items-center justify-between gap-2 mb-4">
      <h2 class="text-lg font-semibold m-0">已发布模板</h2>
      <n-input-group class="!w-80">
        <n-input
          v-model:value="search"
          clearable
          placeholder="搜索名称、作者、发布者或说明"
          @keyup.enter="doSearch"
        />
        <n-button type="primary" ghost @click="doSearch">搜索</n-button>
      </n-input-group>
    </div>

    <n-spin :show="loading">
      <n-empty
        v-if="items.length === 0 && !loading"
        description="暂无已发布模板"
        class="mt-16"
      />
      <div v-else class="overflow-x-auto">
        <n-table :bordered="false" :single-line="false" size="small" class="min-w-[54rem]">
          <thead>
            <tr>
              <th>模板名称</th>
              <th class="w-32">发布者</th>
              <th>说明</th>
              <th class="w-24">版本</th>
              <th class="w-44">更新时间</th>
              <th class="w-24 !text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in items" :key="row.id">
              <td>
                <div class="font-medium" :title="row.name">{{ row.name }}</div>
                <div v-if="row.author" class="text-xs text-gray-400">作者: {{ row.author }}</div>
              </td>
              <td>{{ row.owner }}</td>
              <td class="max-w-md text-xs text-gray-500">
                <span class="line-clamp-2" :title="row.description || ''">{{ row.description || '-' }}</span>
              </td>
              <td>{{ row.version }}</td>
              <td class="text-xs whitespace-nowrap">{{ formatDateTime(row.updated_at) }}</td>
              <td class="!text-right">
                <n-tag v-if="row.owned" size="small" type="info">我的发布</n-tag>
                <n-button
                  v-else
                  size="small"
                  :type="row.installed ? 'default' : 'primary'"
                  :disabled="row.installed"
                  :loading="installingId === row.id"
                  @click="installTemplate(row)"
                >
                  {{ row.installed ? '已安装' : '安装' }}
                </n-button>
              </td>
            </tr>
          </tbody>
        </n-table>
      </div>
      <div v-if="total > pageSize" class="mt-4 flex justify-end">
        <n-pagination
          :page="page"
          :page-size="pageSize"
          :item-count="total"
          :page-sizes="[20, 50, 100]"
          show-size-picker
          @update:page="handlePageChange"
          @update:page-size="handlePageSizeChange"
        />
      </div>
    </n-spin>
  </div>
</template>
