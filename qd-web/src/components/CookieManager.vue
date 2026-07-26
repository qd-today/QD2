<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import api from '@/api'

const props = defineProps<{ taskId: number }>()
const show = defineModel<boolean>('show', { default: false })
const message = useMessage()

const cookies = ref<any[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await api.get(`/api/tasks/${props.taskId}/cookies`)
    cookies.value = res.data.cookies
  } finally {
    loading.value = false
  }
}

async function clearAll() {
  await api.delete(`/api/tasks/${props.taskId}/cookies`)
  message.success('已清空 Cookie 会话')
  await load()
}

watch(show, (v) => {
  if (v) load()
})
</script>

<template>
  <n-modal v-model:show="show" preset="card" title="任务 Cookie 会话" class="max-w-2xl" :style="{ width: '92vw' }">
    <n-spin :show="loading">
      <n-empty v-if="cookies.length === 0 && !loading" description="暂无 Cookie（任务执行后自动保存登录态）" />
      <n-table v-else size="small" :bordered="false">
        <thead>
          <tr><th>名称</th><th>值</th><th>域</th><th>路径</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in cookies" :key="`${c.domain}/${c.name}`">
            <td class="font-mono text-xs">{{ c.name }}</td>
            <td class="font-mono text-xs max-w-48 truncate" :title="c.value">{{ c.value }}</td>
            <td class="text-xs text-gray-400">{{ c.domain || '-' }}</td>
            <td class="text-xs text-gray-400">{{ c.path || '/' }}</td>
          </tr>
        </tbody>
      </n-table>
    </n-spin>
    <template #footer>
      <div class="flex justify-between">
        <n-button size="small" type="error" quaternary :disabled="cookies.length === 0" @click="clearAll">
          清空会话
        </n-button>
        <n-button size="small" @click="load">刷新</n-button>
      </div>
    </template>
  </n-modal>
</template>
