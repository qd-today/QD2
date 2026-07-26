<script setup lang="ts">
import { ref, watch } from 'vue'
import api from '@/api'

const props = defineProps<{ taskId: number; visible: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const loading = ref(false)
const runs = ref<any[]>([])
const showDetail = ref(false)
const selectedRun = ref<any>(null)

function formatTime(iso?: string) {
  return iso ? new Date(iso + 'Z').toLocaleString() : '-'
}

function formatJson(data: any) {
  try {
    return JSON.stringify(JSON.parse(data), null, 2)
  } catch {
    return data
  }
}

async function fetchRuns() {
  if (!props.taskId) return
  loading.value = true
  try {
    const res = await api.get(`/api/tasks/${props.taskId}/runs?page_size=50`)
    runs.value = res.data
  } catch {
    runs.value = []
  } finally {
    loading.value = false
  }
}

watch(
  () => props.visible,
  (val) => {
    if (val) fetchRuns()
  }
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
        <div class="text-sm font-medium mb-1">响应摘要</div>
        <pre
          class="bg-gray-50 dark:bg-gray-800 p-3 rounded text-xs whitespace-pre-wrap break-all max-h-64 overflow-auto"
          >{{ formatJson(selectedRun.response_summary) }}</pre
        >
      </div>
    </n-modal>
  </n-modal>
</template>
