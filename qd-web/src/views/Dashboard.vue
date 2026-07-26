<template>
  <div class="dashboard">
    <h2>{{ t('nav.dashboard') }}</h2>

    <el-row :gutter="20" style="margin-bottom: 24px">
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>{{ t('nav.templates') }}</span>
              <el-button link @click="router.push('/templates')">查看</el-button>
            </div>
          </template>
          <div class="stat-number">{{ stats.templateCount }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span>{{ t('nav.tasks') }}</span>
              <el-button link @click="router.push('/tasks')">查看</el-button>
            </div>
          </template>
          <div class="stat-number">{{ stats.taskCount }}</div>
          <div style="text-align: center; color: #999; font-size: 12px; margin-top: 4px">
            {{ stats.runningCount }} 个运行中
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>最近执行</template>
          <div class="stat-number">{{ stats.totalRuns }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Recent Runs -->
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>最近执行记录</span>
          <el-button link @click="router.push('/tasks')">查看全部</el-button>
        </div>
      </template>
      <el-table :data="recentRuns" stripe size="small" empty-text="暂无执行记录">
        <el-table-column label="任务" min-width="120">
          <template #default="{ row }">
            <span>{{ getTaskName(row.task_id) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">
            {{ row.duration_seconds ? row.duration_seconds.toFixed(1) + 's' : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="执行时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.started_at) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import api from '@/api'

const { t } = useI18n()
const router = useRouter()

const stats = ref({
  templateCount: 0,
  taskCount: 0,
  runningCount: 0,
  totalRuns: 0,
})

const recentRuns = ref<any[]>([])
const allTasks = ref<any[]>([])

function formatTime(iso: string) {
  return new Date(iso).toLocaleString()
}

function getTaskName(taskId: number) {
  return allTasks.value.find((t) => t.id === taskId)?.name || `任务 #${taskId}`
}

onMounted(async () => {
  try {
    const [templatesRes, tasksRes] = await Promise.all([
      api.get('/api/templates?page_size=100'),
      api.get('/api/tasks?page_size=100'),
    ])

    stats.value.templateCount = templatesRes.data.total
    stats.value.taskCount = tasksRes.data.total
    allTasks.value = tasksRes.data.items

    // Count running tasks
    stats.value.runningCount = tasksRes.data.items.filter(
      (t: any) => t.status === 'running'
    ).length

    // Fetch recent runs for each task
    const runPromises = tasksRes.data.items.slice(0, 5).map((task: any) =>
      api.get(`/api/tasks/${task.id}/runs?page_size=5`).catch(() => ({ data: [] }))
    )
    const runResults = await Promise.all(runPromises)
    const allRuns = runResults.flatMap((r: any) => r.data || [])
    allRuns.sort((a: any, b: any) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime())
    recentRuns.value = allRuns.slice(0, 10)
    stats.value.totalRuns = allRuns.length
  } catch {
    // ignore
  }
})
</script>

<style scoped>
.stat-number {
  font-size: 36px;
  font-weight: bold;
  color: #409eff;
  text-align: center;
}
</style>
