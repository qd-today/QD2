<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { useRoute, useRouter } from 'vue-router'
import { useTaskStore } from '@/stores/task'
import api from '@/api'
import TaskRunHistory from '@/components/TaskRunHistory.vue'
import CookieManager from '@/components/CookieManager.vue'

const message = useMessage()
const dialog = useDialog()
const route = useRoute()
const router = useRouter()
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
const selectedTaskIds = ref<number[]>([])
const collapsedTaskGroups = ref<Record<string, boolean>>({})
const showGroupDialog = ref(false)
const newGroupName = ref('')
const showScheduleDialog = ref(false)
const scheduleTaskId = ref<number | null>(null)
const scheduleSaving = ref(false)
const scheduleForm = reactive({
  schedule_type: 'interval',
  interval_seconds: 3600,
  cron_expression: '',
  run_time: '00:00',
})
const showTaskGroupDialog = ref(false)
const groupTaskId = ref<number | null>(null)
const taskGroupValue = ref<number | null>(null)
const groupSaving = ref(false)

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

const taskSections = computed(() => {
  const sectionMap = new Map<string, { id: number | null; name: string; tasks: any[] }>()
  for (const group of groups.value) {
    sectionMap.set(String(group.id), { id: group.id, name: group.name, tasks: [] })
  }
  sectionMap.set('ungrouped', { id: null, name: 'None', tasks: [] })
  for (const task of filteredTasks.value) {
    const key = task.group_id ? String(task.group_id) : 'ungrouped'
    if (!sectionMap.has(key)) sectionMap.set(key, { id: task.group_id || null, name: 'None', tasks: [] })
    sectionMap.get(key)!.tasks.push(task)
  }
  return Array.from(sectionMap.values()).filter((section) => section.tasks.length > 0)
})

const allTasksSelected = computed(
  () => filteredTasks.value.length > 0 && filteredTasks.value.every((task: any) => selectedTaskIds.value.includes(task.id)),
)

function groupKey(id: number | null) {
  return id === null ? 'ungrouped' : String(id)
}

function isTaskGroupCollapsed(id: number | null) {
  return collapsedTaskGroups.value[groupKey(id)] === true
}

function toggleTaskGroup(id: number | null) {
  const key = groupKey(id)
  collapsedTaskGroups.value[key] = !isTaskGroupCollapsed(id)
}

function toggleTaskSelection(id: number, checked: boolean) {
  if (checked && !selectedTaskIds.value.includes(id)) selectedTaskIds.value.push(id)
  if (!checked) selectedTaskIds.value = selectedTaskIds.value.filter((taskId) => taskId !== id)
}

function toggleAllTaskSelection(checked: boolean) {
  selectedTaskIds.value = checked ? filteredTasks.value.map((task: any) => task.id) : []
}

function toggleGroupSelection(tasks: any[], checked: boolean) {
  const ids = new Set(selectedTaskIds.value)
  for (const task of tasks) {
    if (checked) ids.add(task.id)
    else ids.delete(task.id)
  }
  selectedTaskIds.value = Array.from(ids)
}

function isGroupSelected(tasks: any[]) {
  return tasks.length > 0 && tasks.every((task) => selectedTaskIds.value.includes(task.id))
}

function formatDateTime(value?: string | null) {
  if (!value) return '从未'
  const normalized = value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString()
}

function formatScheduleRule(config?: Record<string, unknown>) {
  const schedule = config || {}
  const scheduleType = String(schedule.schedule_type || 'interval')
  if (scheduleType === 'interval') {
    const seconds = Number(schedule.interval_seconds || 3600)
    if (seconds % 86400 === 0) return `每 ${seconds / 86400} 天`
    if (seconds % 3600 === 0) return `每 ${seconds / 3600} 小时`
    if (seconds % 60 === 0) return `每 ${seconds / 60} 分钟`
    return `每 ${seconds} 秒`
  }
  if (scheduleType === 'cron') return `Cron: ${String(schedule.cron_expression || '-')}`
  if (scheduleType === 'daily') return `每天 ${String(schedule.run_time || '00:00')}`
  if (scheduleType === 'once') {
    const runAt = typeof schedule.run_at === 'string' ? schedule.run_at : null
    return runAt ? `单次 ${formatDateTime(runAt)}` : '仅手动'
  }
  return '仅手动'
}

onMounted(async () => {
  await taskStore.fetchTasks()
  await fetchTemplates()
  await fetchGroups()
  const templateId = Number(route.query.template_id)
  if (route.query.create === '1' && Number.isInteger(templateId) && templateId > 0) {
    openCreate(templateId)
    await router.replace('/tasks')
  }
})

async function fetchTemplates() {
  try {
    const res = await api.get('/api/templates?page_size=100')
    templates.value = res.data.items
  } catch {
    message.error('模板列表加载失败')
  }
}

async function fetchGroups() {
  try {
    const res = await api.get('/api/task-groups')
    groups.value = res.data
  } catch {
    message.error('任务分组加载失败')
  }
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

function statusLabel(status?: string): string {
  const labels: Record<string, string> = {
    pending: '等待',
    running: '运行中',
    success: '成功',
    failed: '失败',
    paused: '停止',
    disabled: '停止',
  }
  return labels[status || ''] || '停止'
}

const jinjaGlobals = new Set([
  '_cookies', 'True', 'False', 'none', 'int', 'float', 'bool', 'utf8', 'unicode',
  'urlencode', 'quote_chinese', 'b2a_hex', 'a2b_hex', 'b2a_uu', 'a2b_uu',
  'b2a_base64', 'a2b_base64', 'b2a_qp', 'a2b_qp', 'crc_hqx', 'crc32', 'format',
  'b64decode', 'b64encode', 'to_uuid', 'md5', 'sha1', 'password_hash', 'hash',
  'aes_encrypt', 'aes_decrypt', 'rsa_encrypt', 'rsa_decrypt', 'timestamp',
  'date_time', 'strftime', 'is_num', 'add', 'sub', 'multiply', 'divide', 'Faker',
  'regex_replace', 'regex_escape', 'regex_search', 'regex_findall', 'ternary',
  'random', 'shuffle', 'mandatory', 'type_debug', 'dict', 'lipsum', 'range',
])

function extractVars(templateId: number) {
  const tmpl = templates.value.find((t) => t.id === templateId)
  const firstUse = new Map<string, number>()
  const firstExtract = new Map<string, number>()
  const scan = (value: unknown, requestIndex: number) => {
    if (typeof value !== 'string') return
    for (const m of value.matchAll(/\{\{\s*([A-Za-z_][A-Za-z0-9_]*)/g)) {
      const name = m[1]
      if (!jinjaGlobals.has(name) && !firstUse.has(name)) firstUse.set(name, requestIndex)
    }
  }

  const templateData = tmpl?.template_data
  const entries = Array.isArray(templateData)
    ? templateData.map((entry: any) => ({
        request: entry.request || {},
        rule: entry.rule || entry.request?.rule || {},
      }))
    : Array.isArray(templateData?.requests)
      ? templateData.requests.map((request: any) => ({
          request,
          rule: request.rule || {},
        }))
      : (templateData?.log?.entries || []).map((entry: any) => ({
          request: entry.request || {},
          rule: {
            ...(entry.rule || {}),
            extract_variables: entry.extract_variables || entry.rule?.extract_variables || [],
          },
        }))

  for (const name of Object.keys(templateData?.extractors || {})) {
    firstExtract.set(name, 0)
  }

  entries.forEach(({ request: req, rule }: any, requestIndex: number) => {
    if (!req) return
    scan(req.url, requestIndex)
    for (const header of req.headers || []) {
      scan(header.name, requestIndex)
      scan(header.value, requestIndex)
    }
    for (const query of req.queryString || []) {
      scan(query.name, requestIndex)
      scan(query.value, requestIndex)
    }
    for (const cookie of req.cookies || []) {
      scan(cookie.name, requestIndex)
      scan(cookie.value, requestIndex)
    }
    scan(req.postData?.text || req.data || req.body, requestIndex)

    const extractedNames = new Set<string>(Object.keys(req.extractors || {}))
    for (const extractor of rule.extract_variables || req.extract_variables || []) {
      if (extractor.name) extractedNames.add(extractor.name)
    }
    for (const name of extractedNames) {
      if (!firstExtract.has(name)) firstExtract.set(name, requestIndex)
    }
  })

  const candidates = new Set([...Object.keys(tmpl?.variables || {}), ...firstUse.keys()])
  const requiredVariables = Array.from(candidates).filter((name) => {
    if (jinjaGlobals.has(name)) return false
    const extractIndex = firstExtract.get(name)
    const useIndex = firstUse.get(name)
    return extractIndex === undefined || (useIndex !== undefined && useIndex <= extractIndex)
  })

  templateVariables.value = requiredVariables.map((key) => ({
    key,
    value: String(tmpl?.variables?.[key] ?? ''),
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

function openCreate(templateId?: number) {
  editingId.value = null
  resetForm()
  if (typeof templateId === 'number') {
    const selectedTemplate = templates.value.find((template) => template.id === templateId)
    if (selectedTemplate) {
      form.template_id = templateId
      form.name = selectedTemplate.name
      onTemplateChange(templateId)
    }
  }
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

function openTemplate(row: any) {
  router.push(`/templates/${row.template_id}`)
}

function openSchedule(row: any) {
  const config = row.schedule_config || {}
  scheduleTaskId.value = row.id
  scheduleForm.schedule_type = config.schedule_type || 'interval'
  scheduleForm.interval_seconds = config.interval_seconds || 3600
  scheduleForm.cron_expression = config.cron_expression || ''
  scheduleForm.run_time = config.run_time || '00:00'
  showScheduleDialog.value = true
}

async function saveSchedule() {
  if (!scheduleTaskId.value) return
  const scheduleConfig: Record<string, string | number> = { schedule_type: scheduleForm.schedule_type }
  if (scheduleForm.schedule_type === 'interval') scheduleConfig.interval_seconds = scheduleForm.interval_seconds
  if (scheduleForm.schedule_type === 'cron') scheduleConfig.cron_expression = scheduleForm.cron_expression
  if (scheduleForm.schedule_type === 'daily') scheduleConfig.run_time = scheduleForm.run_time
  scheduleSaving.value = true
  try {
    await taskStore.updateTask(scheduleTaskId.value, { schedule_config: scheduleConfig })
    showScheduleDialog.value = false
    message.success('定时设置已保存')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '定时设置保存失败')
  } finally {
    scheduleSaving.value = false
  }
}

function openTaskGroup(row: any) {
  groupTaskId.value = row.id
  taskGroupValue.value = row.group_id || null
  showTaskGroupDialog.value = true
}

async function saveTaskGroup() {
  if (!groupTaskId.value) return
  groupSaving.value = true
  try {
    await taskStore.updateTask(groupTaskId.value, { group_id: taskGroupValue.value })
    showTaskGroupDialog.value = false
    await fetchGroups()
    message.success('任务分组已保存')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '任务分组保存失败')
  } finally {
    groupSaving.value = false
  }
}

function handleMore(action: string, row: any) {
  if (action === 'cookies') openCookies(row)
  if (action === 'delete') deleteTask(row.id)
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
    window.dispatchEvent(new CustomEvent('qd:open-logs'))
    await nextTick()
    await taskStore.runTask(id)
    message.success('任务执行完成')
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
      <n-button type="primary" @click="openCreate()">新建任务</n-button>
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
      <div v-else class="overflow-x-auto">
        <n-table :bordered="false" :single-line="false" size="small" class="min-w-[63rem]">
          <thead>
            <tr>
              <th class="w-10">
                <n-checkbox
                  :checked="allTasksSelected"
                  :indeterminate="selectedTaskIds.length > 0 && !allTasksSelected"
                  aria-label="选择全部任务"
                  @update:checked="toggleAllTaskSelection"
                />
              </th>
              <th>任务名称</th>
              <th class="w-20">成/败</th>
              <th class="w-32">定时规则</th>
              <th class="w-36">上次成功</th>
              <th class="w-20">状态</th>
              <th class="w-36">下次运行</th>
              <th class="!text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="section in taskSections" :key="groupKey(section.id)">
              <tr class="bg-sky-50 dark:bg-sky-950/40">
                <td colspan="8" class="!py-2">
                  <div class="flex items-center justify-between gap-2">
                    <div class="flex items-center gap-2 font-semibold">
                      <n-checkbox
                        :checked="isGroupSelected(section.tasks)"
                        :indeterminate="section.tasks.some((task) => selectedTaskIds.includes(task.id)) && !isGroupSelected(section.tasks)"
                        :aria-label="`选择${section.name}分组`"
                        @update:checked="toggleGroupSelection(section.tasks, $event)"
                      />
                      <span>{{ section.name }} 分组</span>
                    </div>
                    <n-button
                      size="tiny"
                      quaternary
                      :aria-label="`${isTaskGroupCollapsed(section.id) ? '展开' : '收起'}${section.name}分组`"
                      @click="toggleTaskGroup(section.id)"
                    >
                      {{ isTaskGroupCollapsed(section.id) ? '展开' : '收起' }}
                    </n-button>
                  </div>
                </td>
              </tr>
              <template v-if="!isTaskGroupCollapsed(section.id)">
              <tr v-for="row in section.tasks" :key="row.id">
                <td>
                  <n-checkbox
                    :checked="selectedTaskIds.includes(row.id)"
                    :aria-label="`选择任务 ${row.name}`"
                    @update:checked="toggleTaskSelection(row.id, $event)"
                  />
                </td>
                <td class="font-medium">
                  <n-tag v-if="row.status === 'disabled'" size="tiny" type="warning" class="mr-1">禁用</n-tag>
                  <span :title="row.name">{{ row.name }}</span>
                </td>
                <td class="whitespace-nowrap">
                  <span class="text-green-600 dark:text-green-400">{{ row.success_count ?? 0 }}</span>
                  <span class="text-gray-400"> / </span>
                  <span class="text-red-600 dark:text-red-400">{{ row.failed_count ?? 0 }}</span>
                </td>
                <td class="text-xs whitespace-nowrap" :title="formatScheduleRule(row.schedule_config)">
                  {{ formatScheduleRule(row.schedule_config) }}
                </td>
                <td class="text-xs whitespace-nowrap">{{ formatDateTime(row.last_success_at) }}</td>
                <td>
                  <n-tag :type="statusType(row.status)" size="small" round>{{ statusLabel(row.status) }}</n-tag>
                </td>
                <td class="text-xs whitespace-nowrap">{{ formatDateTime(row.next_run_at) }}</td>
                <td class="!text-right whitespace-nowrap">
                  <n-button size="tiny" quaternary @click="openEdit(row)">修改</n-button>
                  <n-button size="tiny" type="success" quaternary :loading="runningId === row.id" @click="runTask(row.id)">
                    执行
                  </n-button>
                  <n-button size="tiny" quaternary @click="openTemplate(row)">模板</n-button>
                  <n-button size="tiny" quaternary @click="openSchedule(row)">定时</n-button>
                  <n-button size="tiny" quaternary @click="openHistory(row)">日志</n-button>
                  <n-button size="tiny" quaternary @click="openTaskGroup(row)">分组</n-button>
                  <n-dropdown
                    trigger="click"
                    :options="[
                      { label: 'Cookie', key: 'cookies' },
                      { label: '删除', key: 'delete' },
                    ]"
                    @select="(key: string) => handleMore(key, row)"
                  >
                    <n-button size="tiny" quaternary title="更多操作" aria-label="更多操作">⋯</n-button>
                  </n-dropdown>
                </td>
              </tr>
              </template>
            </template>
          </tbody>
        </n-table>
      </div>
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
        <div v-if="templateVariables.length > 0" class="space-y-3 mb-3">
          <div v-for="v in templateVariables" :key="v.key" class="grid grid-cols-1 md:grid-cols-[minmax(12rem,2fr)_minmax(18rem,3fr)] gap-1 md:gap-3 items-center">
            <label class="text-sm break-all" :title="v.key">{{ v.key }}</label>
            <n-input
              v-model:value="form.variables[v.key]"
              :placeholder="v.value || '请输入值'"
              size="small"
              class="w-full"
            />
          </div>
        </div>
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

    <!-- Task schedule -->
    <n-modal
      v-model:show="showScheduleDialog"
      preset="card"
      title="定时设置"
      class="max-w-md"
      :style="{ width: '92vw' }"
    >
      <n-form label-placement="left" label-width="90">
        <n-form-item label="调度类型">
          <n-select
            v-model:value="scheduleForm.schedule_type"
            :options="[
              { label: '固定间隔', value: 'interval' },
              { label: 'Cron 表达式', value: 'cron' },
              { label: '每天执行', value: 'daily' },
              { label: '仅手动', value: 'once' },
            ]"
          />
        </n-form-item>
        <n-form-item v-if="scheduleForm.schedule_type === 'interval'" label="间隔(秒)">
          <n-input-number v-model:value="scheduleForm.interval_seconds" :min="10" :max="86400" class="w-full" />
        </n-form-item>
        <n-form-item v-if="scheduleForm.schedule_type === 'cron'" label="Cron">
          <n-input v-model:value="scheduleForm.cron_expression" placeholder="0 */6 * * *" />
        </n-form-item>
        <n-form-item v-if="scheduleForm.schedule_type === 'daily'" label="执行时间">
          <n-time-picker
            v-model:formatted-value="scheduleForm.run_time"
            format="HH:mm"
            value-format="HH:mm"
            class="w-full"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="showScheduleDialog = false">取消</n-button>
          <n-button type="primary" :loading="scheduleSaving" @click="saveSchedule">保存</n-button>
        </div>
      </template>
    </n-modal>

    <!-- Task group -->
    <n-modal
      v-model:show="showTaskGroupDialog"
      preset="card"
      title="任务分组"
      class="max-w-md"
      :style="{ width: '92vw' }"
    >
      <n-select
        v-model:value="taskGroupValue"
        :options="groups.map((group) => ({ label: group.name, value: group.id }))"
        placeholder="选择分组"
        clearable
      />
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="showTaskGroupDialog = false">取消</n-button>
          <n-button type="primary" :loading="groupSaving" @click="saveTaskGroup">保存</n-button>
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
