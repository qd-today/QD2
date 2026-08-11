<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import api from '@/api'

const props = defineProps<{ taskId: number; visible: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()
const dialog = useDialog()
const message = useMessage()

const loading = ref(false)
const runs = ref<any[]>([])
const stats = ref({ total: 0, success: 0, failed: 0, other: 0 })

function formatTime(iso?: string) {
  return iso ? new Date(iso + 'Z').toLocaleString() : '-'
}

function runLog(row: any): string {
  return row.response_summary || row.error_message || '-'
}

async function fetchRuns() {
  if (!props.taskId) return
  loading.value = true
  try {
    const [runsResponse, statsResponse] = await Promise.all([
      api.get(`/api/tasks/${props.taskId}/runs?page_size=50`),
      api.get(`/api/tasks/${props.taskId}/runs/stats`),
    ])
    runs.value = runsResponse.data
    stats.value = statsResponse.data
  } catch {
    runs.value = []
    stats.value = { total: 0, success: 0, failed: 0, other: 0 }
  } finally {
    loading.value = false
  }
}

function clearRuns(status?: 'success' | 'failed') {
  const label = status === 'success' ? '成功日志' : status === 'failed' ? '失败日志' : '全部日志'
  dialog.warning({
    title: '清理执行历史',
    content: `确认删除${label}？此操作无法撤销。`,
    positiveText: '删除',
    negativeText: '取消',
    async onPositiveClick() {
      await api.delete(`/api/tasks/${props.taskId}/runs`, {
        params: status ? { status } : {},
      })
      message.success(`${label}已删除`)
      await fetchRuns()
    },
  })
}

watch(
  () => [props.visible, props.taskId] as const,
  ([visible]) => {
    if (visible) fetchRuns()
  },
  { immediate: true }
)
</script>

<template>
  <n-modal
    :show="visible"
    preset="card"
    title="任务执行日志"
    class="max-w-5xl"
    :style="{ width: '92vw' }"
    @update:show="emit('close')"
  >
    <div class="flex flex-wrap items-center gap-2 mb-3">
      <n-tag size="small">总计 {{ stats.total }}</n-tag>
      <n-tag size="small" type="success">成功 {{ stats.success }}</n-tag>
      <n-tag size="small" type="error">失败 {{ stats.failed }}</n-tag>
      <div class="flex-1" />
      <n-button size="tiny" tertiary @click="clearRuns('success')">清理成功</n-button>
      <n-button size="tiny" tertiary @click="clearRuns('failed')">清理失败</n-button>
      <n-button size="tiny" tertiary type="error" @click="clearRuns()">清理全部</n-button>
    </div>
    <n-spin :show="loading">
      <n-empty v-if="runs.length === 0 && !loading" description="暂无执行记录" />
      <div v-else class="overflow-x-auto">
        <n-table size="small" :bordered="true" :single-line="false" class="min-w-3xl table-fixed">
          <thead>
            <tr>
              <th class="w-48">时间</th>
              <th class="w-24">状态</th>
              <th>日志</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in runs" :key="row.id">
              <td class="text-xs whitespace-nowrap">{{ formatTime(row.started_at) }}</td>
              <td>
                <n-tag :type="row.status === 'success' ? 'success' : 'error'" size="small" round>
                  {{ row.status === 'success' ? '成功' : '失败' }}
                </n-tag>
              </td>
              <td>
                <pre
                  class="m-0 text-xs leading-5 whitespace-pre-wrap break-words font-mono text-gray-800 dark:text-gray-100"
                  :class="row.status === 'success' ? '' : 'text-red-600 dark:text-red-400'"
                >{{ runLog(row) }}</pre>
              </td>
            </tr>
          </tbody>
        </n-table>
      </div>
    </n-spin>
  </n-modal>
</template>
