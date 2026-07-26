<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { useTaskStore } from '@/stores/task'
import api from '@/api'
import TaskRunHistory from '@/components/TaskRunHistory.vue'
import CookieManager from '@/components/CookieManager.vue'

const message = useMessage()
const dialog = useDialog()
const taskStore = useTaskStore()

const showDialog = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const runningId = ref<number | null>(null)

const showHistory = ref(false)
const historyTaskId = ref<number | null>(null)

const showCookies = ref(false)
const cookieTaskId = ref<number | null>(null)

const templates = ref<any[]>([])
const groups = ref<any[]>([])
const selectedGroupId = ref<number | null>(null)
const showGroupDialog = ref(false)
const newGroupName = ref('')

const templateVariables = ref<{ key: string; value: string }[]>([])

const form = reactive({
  name: '',
  description: '',
  template_id: null as number | null,
  group_id: null as number | null,
  schedule_type: 'interval',
  interval_seconds: 3600,
  cron_expression: '',
  run_time: '00:00',
  variables: {} as Record<string, string>,
  // execution config
  retry_count: 0,
  retry_interval_seconds: 30,
  random_delay_min: 0,
  random_delay_max: 0,
  proxy: '',
})

const filteredTasks = computed(() => {
  if (!selectedGroupId.value) return taskStore.tasks
  return taskStore.tasks.filter((t: any) => t.group_id === selectedGroupId.value)
})

onMounted(async () => {
  await taskStore.fetchTasks()
  await fetchTemplates()
  await fetchGroups()
})

async function fetchTemplates() {
  try {
    const res = await api.get('/api/templates?page_size=100')
    templates.value = res.data.items
  } catch {}
}

async function fetchGroups() {
  try {
    const res = await api.get('/api/task-groups')
    groups.value = res.data
  } catch {}
}

function getTemplateName(id: number) {
  return templates.value.find((t) => t.id === id)?.name
}
function getGroupName(id: number | null) {
  return groups.value.find((g) => g.id === id)?.name
}

function statusType(status: string): any {
  const m: Record<string, string> = {
    success: 'success',
    failed: 'error',
    running: 'warning',
    pending: 'info',
    paused: 'default',
  }
  return m[status] || 'default'
}

function scheduleText(row: any): string {
  const sc = row.schedule_config || {}
  if (sc.schedule_type === 'interval') return `每 ${sc.interval_seconds} 秒`
  if (sc.schedule_type === 'cron') return sc.cron_expression || 'cron'
  if (sc.schedule_type === 'daily') return `每天 ${sc.run_time}`
  return '仅手动'
}

function extractVars(templateId: number) {
  const tmpl = templates.value.find((t) => t.id === templateId)
  const vars = new Set<string>()
  const scan = (s?: string) => {
    for (const m of (s || '').matchAll(/\{\{\s*(\w+)/g)) {
      const name = m[1]
      if (!['timestamp', 'date_time', 'random', 'add', 'sub'].includes(name)) vars.add(name)
    }
  }
  const reqs = Array.isArray(tmpl?.template_data)
    ? tmpl.template_data.map((e: any) => e.request)
    : tmpl?.template_data?.requests || []
  for (const req of reqs) {
    if (!req) continue
    scan(req.url)
    for (const h of req.headers || []) scan(h.value)
    scan(req.postData?.text || req.data)
  }
  templateVariables.value = Array.from(vars).map((key) => ({
    key,
    value: tmpl?.variables?.[key] || '',
  }))
}

function onTemplateChange(templateId: number) {
  extractVars(templateId)
  const next: Record<string, string> = {}
  templateVariables.value.forEach((v) => {
    next[v.key] = form.variables[v.key] ?? v.value
  })
  form.variables = next
}

function resetForm() {
  form.name = ''
  form.description = ''
  form.template_id = null
  form.group_id = null
  form.schedule_type = 'interval'
  form.interval_seconds = 3600
  form.cron_expression = ''
  form.run_time = '00:00'
  form.variables = {}
  form.retry_count = 0
  form.retry_interval_seconds = 30
  form.random_delay_min = 0
  form.random_delay_max = 0
  form.proxy = ''
  templateVariables.value = []
}

function openCreate() {
  editingId.value = null
  resetForm()
  showDialog.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  resetForm()
  form.name = row.name
  form.description = row.description || ''
  form.template_id = row.template_id
  form.group_id = row.group_id
  form.schedule_type = row.schedule_config?.schedule_type || 'interval'
  form.interval_seconds = row.schedule_config?.interval_seconds || 3600
  form.cron_expression = row.schedule_config?.cron_expression || ''
  form.run_time = row.schedule_config?.run_time || '00:00'
  form.variables = { ...(row.variables || {}) }
  const ec = row.execution_config || {}
  form.retry_count = ec.retry_count || 0
  form.retry_interval_seconds = ec.retry_interval_seconds ?? 30
  form.random_delay_min = ec.random_delay_min || 0
  form.random_delay_max = ec.random_delay_max || 0
  form.proxy = ec.proxy || ''
  onTemplateChange(row.template_id)
  showDialog.value = true
}

function openHistory(row: any) {
  historyTaskId.value = row.id
  showHistory.value = true
}

function openCookies(row: any) {
  cookieTaskId.value = row.id
  showCookies.value = true
}

async function save() {
  if (!form.name || !form.template_id) {
    message.warning('请填写任务名称并选择模板')
    return
  }
  const scheduleConfig: any = { schedule_type: form.schedule_type }
  if (form.schedule_type === 'interval') scheduleConfig.interval_seconds = form.interval_seconds
  if (form.schedule_type === 'cron') scheduleConfig.cron_expression = form.cron_expression
  if (form.schedule_type === 'daily') scheduleConfig.run_time = form.run_time

  const data: any = {
    name: form.name,
    description: form.description,
    template_id: form.template_id!,
    group_id: form.group_id || undefined,
    schedule_config: scheduleConfig,
    variables: form.variables,
    execution_config: {
      retry_count: form.retry_count,
      retry_interval_seconds: form.retry_interval_seconds,
      random_delay_min: form.random_delay_min,
      random_delay_max: form.random_delay_max,
      proxy: form.proxy || '',
    },
  }

  saving.value = true
  try {
    if (editingId.value) {
      await taskStore.updateTask(editingId.value, data)
    } else {
      await taskStore.createTask(data)
    }
    showDialog.value = false
    message.success('保存成功')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function runTask(id: number) {
  runningId.value = id
  try {
    await taskStore.runTask(id)
    message.success('任务已执行，可在右上角「实时日志」查看详情')
    await taskStore.fetchTasks()
  } catch {
    message.error('执行失败')
  } finally {
    runningId.value = null
  }
}

function deleteTask(id: number) {
  dialog.warning({
    title: '删除任务',
    content: '确定删除该任务？',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      await taskStore.deleteTask(id)
      message.success('已删除')
    },
  })
}

async function createGroup() {
  if (!newGroupName.value.trim()) {
    message.warning('请输入分组名称')
    return
  }
  try {
    await api.post('/api/task-groups', { name: newGroupName.value })
    newGroupName.value = ''
    await fetchGroups()
    message.success('创建成功')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '创建失败')
  }
}

function deleteGroup(id: number) {
  dialog.warning({
    title: '删除分组',
    content: '确定删除该分组？组内任务将变为未分组。',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      await api.delete(`/api/task-groups/${id}`)
      await fetchGroups()
      message.success('已删除')
    },
  })
}
</script>

<template>
  <div>
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-lg font-semibold m-0">任务管理</h2>
      <n-button type="primary" @click="openCreate">新建任务</n-button>
    </div>

    <div v-if="groups.length > 0" class="mb-3 flex flex-wrap gap-2">
      <n-tag
        v-for="g in groups"
        :key="g.id"
        :type="selectedGroupId === g.id ? 'primary' : 'default'"
        round
        class="cursor-pointer"
        @click="selectedGroupId = selectedGroupId === g.id ? null : g.id"
      >
        {{ g.name }} ({{ g.task_count }})
      </n-tag>
      <n-tag v-if="selectedGroupId" closable round @close="selectedGroupId = null">清除筛选</n-tag>
      <n-button size="tiny" quaternary @click="showGroupDialog = true">管理分组</n-button>
    </div>

    <n-spin :show="taskStore.loading">
      <n-empty
        v-if="filteredTasks.length === 0 && !taskStore.loading"
        description="暂无任务"
        class="mt-16"
      />
      <n-table v-else :bordered="false" :single-line="false" size="small">
        <thead>
          <tr>
            <th>任务名称</th>
            <th>模板</th>
            <th>分组</th>
            <th>调度</th>
            <th>状态</th>
            <th>次数</th>
            <th>重试</th>
            <th class="!text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredTasks" :key="row.id">
            <td class="font-medium">{{ row.name }}</td>
            <td class="text-gray-400">{{ getTemplateName(row.template_id) || `#${row.template_id}` }}</td>
            <td>
              <n-tag v-if="getGroupName(row.group_id)" size="tiny" round>{{ getGroupName(row.group_id) }}</n-tag>
              <span v-else class="text-gray-300">-</span>
            </td>
            <td class="text-xs">{{ scheduleText(row) }}</td>
            <td>
              <n-tag :type="statusType(row.last_status || row.status)" size="small" round>
                {{ row.last_status || row.status }}
              </n-tag>
            </td>
            <td>{{ row.run_count }}</td>
            <td class="text-xs text-gray-400">
              {{ row.execution_config?.retry_count ? `×${row.execution_config.retry_count}` : '-' }}
            </td>
            <td class="!text-right whitespace-nowrap">
              <n-button size="tiny" type="success" quaternary :loading="runningId === row.id" @click="runTask(row.id)">
                执行
              </n-button>
              <n-button size="tiny" quaternary @click="openHistory(row)">历史</n-button>
              <n-button size="tiny" quaternary @click="openCookies(row)">Cookie</n-button>
              <n-button size="tiny" quaternary @click="openEdit(row)">编辑</n-button>
              <n-button size="tiny" quaternary type="error" @click="deleteTask(row.id)">删除</n-button>
            </td>
          </tr>
        </tbody>
      </n-table>
    </n-spin>

    <!-- Create/Edit -->
    <n-modal
      v-model:show="showDialog"
      preset="card"
      :title="editingId ? '编辑任务' : '新建任务'"
      class="max-w-2xl"
      :style="{ width: '92vw' }"
    >
      <n-form label-placement="left" label-width="100">
        <n-form-item label="任务名称" required>
          <n-input v-model:value="form.name" placeholder="任务名称" />
        </n-form-item>
        <n-form-item label="关联模板" required>
          <n-select
            v-model:value="form.template_id"
            :options="templates.map((t) => ({ label: t.name, value: t.id }))"
            placeholder="选择模板"
            filterable
            @update:value="onTemplateChange"
          />
        </n-form-item>
        <n-form-item label="分组">
          <n-select
            v-model:value="form.group_id"
            :options="groups.map((g) => ({ label: g.name, value: g.id }))"
            placeholder="选择分组（可选）"
            clearable
          />
        </n-form-item>
        <n-form-item label="描述">
          <n-input v-model:value="form.description" type="textarea" :rows="2" />
        </n-form-item>

        <n-divider title-placement="left" class="!my-2 !text-xs">模板变量</n-divider>
        <template v-if="templateVariables.length > 0">
          <n-form-item v-for="v in templateVariables" :key="v.key" :label="v.key">
            <n-input
              v-model:value="form.variables[v.key]"
              :placeholder="v.value || '请输入值'"
              size="small"
            />
          </n-form-item>
        </template>
        <div v-else class="text-xs text-gray-400 mb-2 pl-2">该模板无需变量</div>

        <n-divider title-placement="left" class="!my-2 !text-xs">调度设置</n-divider>
        <n-form-item label="调度类型">
          <n-select
            v-model:value="form.schedule_type"
            :options="[
              { label: '固定间隔', value: 'interval' },
              { label: 'Cron 表达式', value: 'cron' },
              { label: '每天执行', value: 'daily' },
              { label: '仅手动', value: 'once' },
            ]"
          />
        </n-form-item>
        <n-form-item v-if="form.schedule_type === 'interval'" label="间隔(秒)">
          <n-input-number v-model:value="form.interval_seconds" :min="10" :max="86400" />
        </n-form-item>
        <n-form-item v-if="form.schedule_type === 'cron'" label="Cron">
          <n-input v-model:value="form.cron_expression" placeholder="0 */6 * * *" />
        </n-form-item>
        <n-form-item v-if="form.schedule_type === 'daily'" label="执行时间">
          <n-time-picker v-model:formatted-value="form.run_time" format="HH:mm" value-format="HH:mm" />
        </n-form-item>

        <n-divider title-placement="left" class="!my-2 !text-xs">执行选项 (重试/延迟/代理)</n-divider>
        <n-form-item label="失败重试">
          <n-input-number v-model:value="form.retry_count" :min="0" :max="10" class="w-28" />
          <span class="text-xs text-gray-400 ml-2">次，间隔</span>
          <n-input-number v-model:value="form.retry_interval_seconds" :min="1" :max="3600" class="w-28 ml-2" />
          <span class="text-xs text-gray-400 ml-2">秒</span>
        </n-form-item>
        <n-form-item label="随机延迟">
          <n-input-number v-model:value="form.random_delay_min" :min="0" class="w-28" />
          <span class="text-xs text-gray-400 mx-2">~</span>
          <n-input-number v-model:value="form.random_delay_max" :min="0" class="w-28" />
          <span class="text-xs text-gray-400 ml-2">秒 (定时触发前随机等待，手动执行跳过)</span>
        </n-form-item>
        <n-form-item label="代理">
          <n-input v-model:value="form.proxy" placeholder="http://host:port 或 socks5://host:port (留空不用)" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="showDialog = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
        </div>
      </template>
    </n-modal>

    <!-- Groups -->
    <n-modal v-model:show="showGroupDialog" preset="card" title="分组管理" class="max-w-md" :style="{ width: '92vw' }">
      <div class="flex gap-2 mb-3">
        <n-input v-model:value="newGroupName" placeholder="新分组名称" />
        <n-button type="primary" @click="createGroup">添加</n-button>
      </div>
      <n-table size="small" :bordered="false">
        <thead>
          <tr><th>分组名</th><th>任务数</th><th class="!text-right">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="g in groups" :key="g.id">
            <td>{{ g.name }}</td>
            <td>{{ g.task_count }}</td>
            <td class="!text-right">
              <n-button size="tiny" quaternary type="error" @click="deleteGroup(g.id)">删除</n-button>
            </td>
          </tr>
        </tbody>
      </n-table>
    </n-modal>

    <TaskRunHistory
      v-if="historyTaskId"
      :task-id="historyTaskId"
      :visible="showHistory"
      @close="showHistory = false"
    />
    <CookieManager v-if="cookieTaskId" v-model:show="showCookies" :task-id="cookieTaskId" />
  </div>
</template>
