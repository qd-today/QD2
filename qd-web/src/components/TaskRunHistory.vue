<template>
  <div class="task-run-history">
    <el-dialog :model-value="visible" title="执行历史" width="800px" @update:model-value="$emit('close')">
      <el-table :data="runs" stripe size="small" v-loading="loading" empty-text="暂无执行记录">
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === 'success' ? '✅ 成功' : '❌ 失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="80">
          <template #default="{ row }">
            {{ row.duration_seconds ? row.duration_seconds.toFixed(1) + 's' : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.started_at) }}
          </template>
        </el-table-column>
        <el-table-column label="错误信息" min-width="200">
          <template #default="{ row }">
            <span v-if="row.error_message" style="color: #f56c6c">{{ row.error_message }}</span>
            <span v-else style="color: #999">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" link @click="showDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Detail Dialog -->
      <el-dialog v-model="showDetailDialog" title="执行详情" width="700px" append-to-body>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="状态">
            <el-tag :type="selectedRun?.status === 'success' ? 'success' : 'danger'">
              {{ selectedRun?.status }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="耗时">
            {{ selectedRun?.duration_seconds?.toFixed(2) }}s
          </el-descriptions-item>
          <el-descriptions-item label="开始时间">
            {{ formatTime(selectedRun?.started_at) }}
          </el-descriptions-item>
          <el-descriptions-item label="结束时间">
            {{ formatTime(selectedRun?.finished_at) }}
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="selectedRun?.error_message" style="margin-top: 16px">
          <h4>错误信息</h4>
          <pre class="error-log">{{ selectedRun.error_message }}</pre>
        </div>

        <div v-if="selectedRun?.response_summary" style="margin-top: 16px">
          <h4>响应摘要</h4>
          <pre class="response-log">{{ formatJson(selectedRun.response_summary) }}</pre>
        </div>
      </el-dialog>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import api from '@/api'

const props = defineProps<{
  taskId: number
  visible: boolean
}>()

defineEmits<{
  (e: 'close'): void
}>()

const loading = ref(false)
const runs = ref<any[]>([])
const showDetailDialog = ref(false)
const selectedRun = ref<any>(null)

function formatTime(iso: string) {
  return iso ? new Date(iso).toLocaleString() : '-'
}

function formatJson(data: any) {
  try {
    return JSON.stringify(JSON.parse(data), null, 2)
  } catch {
    return data
  }
}

function showDetail(run: any) {
  selectedRun.value = run
  showDetailDialog.value = true
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

watch(() => props.visible, (val) => {
  if (val) fetchRuns()
})
</script>

<style scoped>
.error-log, .response-log {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  font-size: 12px;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow: auto;
}
.error-log {
  background: #fef0f0;
  color: #f56c6c;
}
h4 {
  margin: 0 0 8px 0;
  color: #303133;
}
</style>
