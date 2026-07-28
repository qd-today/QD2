<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import api from '@/api'

const router = useRouter()
const message = useMessage()

const stats = ref({ templates: 0, tasks: 0, success: 0, failed: 0 })
const recentRuns = ref<any[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const [tplRes, taskRes] = await Promise.all([
      api.get('/api/templates', { params: { page_size: 1 } }),
      api.get('/api/tasks', { params: { page_size: 100 } }),
    ])
    stats.value.templates = tplRes.data.total
    stats.value.tasks = taskRes.data.total
    const tasks = taskRes.data.items
    stats.value.success = tasks.filter((t: any) => t.last_status === 'success').length
    stats.value.failed = tasks.filter((t: any) => t.last_status === 'failed').length

    // recent runs across first tasks
    const runsAll: any[] = []
    let historyLoadFailed = false
    for (const t of tasks.slice(0, 5)) {
      try {
        const r = await api.get(`/api/tasks/${t.id}/runs`, { params: { page_size: 5 } })
        for (const run of r.data) runsAll.push({ ...run, task_name: t.name })
      } catch {
        historyLoadFailed = true
      }
    }
    if (historyLoadFailed) message.warning('部分执行记录加载失败')
    runsAll.sort((a, b) => (b.started_at > a.started_at ? 1 : -1))
    recentRuns.value = runsAll.slice(0, 10)
  } catch {
    message.error('仪表盘加载失败')
  } finally {
    loading.value = false
  }
})

const cards = [
  { key: 'templates', label: '模板总数', color: 'bg-indigo-500', to: '/templates' },
  { key: 'tasks', label: '任务总数', color: 'bg-blue-500', to: '/tasks' },
  { key: 'success', label: '最近成功', color: 'bg-green-500', to: '/tasks' },
  { key: 'failed', label: '最近失败', color: 'bg-red-500', to: '/tasks' },
]
</script>

<template>
  <div>
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <n-card
        v-for="c in cards"
        :key="c.key"
        hoverable
        class="cursor-pointer rounded-xl"
        @click="router.push(c.to)"
      >
        <div class="flex items-center gap-4">
          <div :class="[c.color, 'w-3 h-12 rounded-full']" />
          <div>
            <div class="text-3xl font-bold">
              {{ (stats as any)[c.key] }}
            </div>
            <div class="text-gray-400 text-sm">{{ c.label }}</div>
          </div>
        </div>
      </n-card>
    </div>

    <n-card title="最近执行记录" class="rounded-xl" :loading="loading">
      <n-empty v-if="recentRuns.length === 0 && !loading" description="暂无执行记录" />
      <n-timeline v-else>
        <n-timeline-item
          v-for="run in recentRuns"
          :key="run.id"
          :type="run.status === 'success' ? 'success' : 'error'"
          :title="run.task_name"
          :content="run.error_message || (run.status === 'success' ? '执行成功' : '执行失败')"
          :time="`${new Date(run.started_at + 'Z').toLocaleString()} · ${run.duration_seconds?.toFixed(1) ?? '-'}s`"
        />
      </n-timeline>
    </n-card>
  </div>
</template>
