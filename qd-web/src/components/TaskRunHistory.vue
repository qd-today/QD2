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
const showDetail = ref(false)
const selectedRun = ref<any>(null)

function formatTime(iso?: string) {
  return iso ? new Date(iso + 'Z').toLocaleString() : '-'
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
    title="执行历史"
    class="max-w-3xl"
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
      <n-table v-else size="small" :bordered="false">
        <thead>
          <tr>
            <th>状态</th>
            <th>耗时</th>
            <th>开始时间</th>
            <th>错误信息</th>
            <th class="!text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in runs" :key="row.id">
            <td>
              <n-tag :type="row.status === 'success' ? 'success' : 'error'" size="small" round>
                {{ row.status === 'success' ? '成功' : '失败' }}
              </n-tag>
            </td>
            <td>{{ row.duration_seconds ? row.duration_seconds.toFixed(1) + 's' : '-' }}</td>
            <td class="text-xs">{{ formatTime(row.started_at) }}</td>
            <td class="text-xs text-red-400 max-w-64 truncate" :title="row.error_message">
              {{ row.error_message || '-' }}
            </td>
            <td class="!text-right">
              <n-button size="tiny" quaternary @click="((selectedRun = row), (showDetail = true))">
                详情
              </n-button>
            </td>
          </tr>
        </tbody>
      </n-table>
    </n-spin>

    <n-modal
      v-model:show="showDetail"
      preset="card"
      title="执行详情"
      class="max-w-2xl"
      :style="{ width: '92vw' }"
    >
      <n-descriptions :column="2" bordered size="small">
        <n-descriptions-item label="状态">
          <n-tag :type="selectedRun?.status === 'success' ? 'success' : 'error'" size="small">
            {{ selectedRun?.status }}
          </n-tag>
        </n-descriptions-item>
        <n-descriptions-item label="耗时">
          {{ selectedRun?.duration_seconds?.toFixed(2) }}s
        </n-descriptions-item>
        <n-descriptions-item label="开始时间">
          {{ formatTime(selectedRun?.started_at) }}
        </n-descriptions-item>
        <n-descriptions-item label="结束时间">
          {{ formatTime(selectedRun?.finished_at) }}
        </n-descriptions-item>
      </n-descriptions>

      <div v-if="selectedRun?.error_message" class="mt-4">
        <div class="text-sm font-medium mb-1">错误信息</div>
        <pre
          class="bg-red-50 dark:bg-red-950 text-red-500 p-3 rounded text-xs whitespace-pre-wrap break-all max-h-64 overflow-auto"
          >{{ selectedRun.error_message }}</pre
        >
      </div>

      <div v-if="selectedRun?.response_summary" class="mt-4">
        <div class="text-sm font-medium mb-1">任务日志 (__log__)</div>
        <pre
          class="bg-gray-50 text-gray-800 dark:bg-gray-800 dark:text-gray-100 p-3 rounded text-xs whitespace-pre-wrap break-all max-h-64 overflow-auto"
          >{{ selectedRun.response_summary }}</pre
        >
      </div>
    </n-modal>
  </n-modal>
</template>
