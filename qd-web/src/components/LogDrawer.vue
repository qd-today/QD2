<script setup lang="ts">
import { onBeforeUnmount, ref, watch, nextTick } from 'vue'
import Cookies from 'js-cookie'

const show = defineModel<boolean>('show', { default: false })

interface LogEvent {
  type: string
  time: string
  task_name?: string
  task_id?: number
  status?: string
  duration?: number
  error?: string
  attempt?: number
  request_index?: number
  success?: boolean
  status_code?: number
  url?: string
  message?: string
  replay?: boolean
}

const events = ref<LogEvent[]>([])
const connected = ref(false)
let ws: WebSocket | null = null
const listRef = ref<HTMLElement | null>(null)

function connect() {
  if (ws) return
  const token = Cookies.get('access_token') || ''
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${location.host}/api/ws/logs?token=${token}`)
  ws.onopen = () => (connected.value = true)
  ws.onclose = () => {
    connected.value = false
    ws = null
  }
  ws.onmessage = (e) => {
    const ev: LogEvent = JSON.parse(e.data)
    if (ev.type === 'ping') return
    events.value.push(ev)
    if (events.value.length > 500) events.value.splice(0, events.value.length - 500)
    nextTick(() => {
      listRef.value?.scrollTo({ top: listRef.value.scrollHeight })
    })
  }
}

function disconnect() {
  ws?.close()
  ws = null
}

watch(show, (v) => {
  if (v) connect()
})

onBeforeUnmount(disconnect)

function eventColor(ev: LogEvent): string {
  if (ev.type === 'task_finish') return ev.status === 'success' ? 'text-green-500' : 'text-red-500'
  if (ev.type === 'task_retry') return 'text-yellow-500'
  if (ev.type === 'request_done') return ev.success ? 'text-gray-400' : 'text-red-400'
  return 'text-blue-400'
}

function eventText(ev: LogEvent): string {
  switch (ev.type) {
    case 'task_start':
      return `▶ 任务「${ev.task_name}」开始执行`
    case 'task_retry':
      return `↻ 任务「${ev.task_name}」第 ${ev.attempt} 次尝试`
    case 'request_done':
      return `  · 请求 #${(ev.request_index ?? 0) + 1} ${ev.success ? '✓' : '✗'} [${ev.status_code ?? '-'}] ${ev.url || ''} ${ev.message ? '— ' + ev.message : ''}`
    case 'task_finish':
      return `■ 任务「${ev.task_name}」${ev.status === 'success' ? '成功' : '失败'} (${ev.duration}s)${ev.error ? ' — ' + ev.error : ''}`
    default:
      return JSON.stringify(ev)
  }
}
</script>

<template>
  <n-drawer v-model:show="show" :width="560" placement="right">
    <n-drawer-content closable>
      <template #header>
        <div class="flex items-center gap-2">
          <span>实时执行日志</span>
          <n-tag :type="connected ? 'success' : 'error'" size="small" round>
            {{ connected ? '已连接' : '未连接' }}
          </n-tag>
        </div>
      </template>
      <div
        ref="listRef"
        class="h-full overflow-y-auto font-mono text-xs leading-5 whitespace-pre-wrap break-all"
      >
        <div v-if="events.length === 0" class="text-gray-400 text-center mt-8">
          暂无日志 — 运行任务后此处将实时显示执行过程
        </div>
        <div v-for="(ev, i) in events" :key="i" :class="[eventColor(ev), ev.replay ? 'opacity-60' : '']">
          <span class="text-gray-500 mr-1">{{ ev.time }}</span>{{ eventText(ev) }}
        </div>
      </div>
      <template #footer>
        <n-button size="small" @click="events = []">清空</n-button>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>
