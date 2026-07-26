<template>
  <div class="tasks">
    <div class="page-header">
      <h2>{{ t('task.title') }}</h2>
      <el-button type="primary" @click="openCreate">{{ t('task.create') }}</el-button>
    </div>

    <!-- Task Groups -->
    <div v-if="groups.length > 0" style="margin-bottom: 16px">
      <el-tag
        v-for="g in groups"
        :key="g.id"
        :type="(selectedGroupId === g.id ? 'primary' : 'info') as any"
        :color="selectedGroupId === g.id ? (g.color || '#409eff') : undefined"
        style="margin-right: 8px; cursor: pointer"
        @click="selectedGroupId = selectedGroupId === g.id ? null : g.id"
      >
        {{ g.name }} ({{ g.task_count }})
      </el-tag>
      <el-tag v-if="selectedGroupId" type="info" closable @close="selectedGroupId = null">清除筛选</el-tag>
    </div>

    <el-table :data="filteredTasks" v-loading="taskStore.loading" stripe>
      <el-table-column prop="name" label="任务名称" min-width="150" />
      <el-table-column label="分组" width="100">
        <template #default="{ row }">
          <el-tag v-if="getGroupName(row.group_id)" size="small" type="info">{{ getGroupName(row.group_id) }}</el-tag>
          <span v-else style="color: #ccc">-</span>
        </template>
      </el-table-column>
      <el-table-column label="关联模板" min-width="120">
        <template #default="{ row }">
          <span v-if="getTemplateName(row.template_id)">{{ getTemplateName(row.template_id) }}</span>
          <span v-else style="color: #999">模板 #{{ row.template_id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="调度" min-width="150">
        <template #default="{ row }">
          <span v-if="row.schedule_config?.schedule_type === 'interval'">每 {{ row.schedule_config.interval_seconds }} 秒</span>
          <span v-else-if="row.schedule_config?.schedule_type === 'cron'">{{ row.schedule_config.cron_expression }}</span>
          <span v-else-if="row.schedule_config?.schedule_type === 'daily'">每天 {{ row.schedule_config.run_time }}</span>
          <span v-else>仅手动</span>
        </template>
      </el-table-column>
      <el-table-column prop="run_count" label="执行次数" width="80" />
      <el-table-column label="操作" width="300" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="success" :loading="runningId === row.id" @click="runTask(row.id)">执行</el-button>
          <el-button size="small" @click="openHistory(row)">历史</el-button>
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteTask(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="showDialog" :title="editingId ? '编辑任务' : t('task.create')" width="650px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="任务名称" required>
          <el-input v-model="form.name" placeholder="任务名称" />
        </el-form-item>
        <el-form-item label="关联模板" required>
          <el-select v-model="form.template_id" placeholder="选择模板" style="width: 100%" @change="onTemplateChange">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="分组">
          <div style="display: flex; gap: 8px; align-items: center">
            <el-select v-model="form.group_id" placeholder="选择分组（可选）" clearable style="flex: 1">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
            <el-button size="small" @click="showGroupDialog = true">管理</el-button>
          </div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>

        <!-- Template Variables -->
        <el-form-item v-if="templateVariables.length > 0" label="模板变量">
          <div style="width: 100%">
            <div v-for="v in templateVariables" :key="v.key" style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px">
              <span style="width: 120px; font-size: 13px; font-family: monospace; color: #606266">{{ v.key }}</span>
              <el-input
                v-model="form.variables[v.key]"
                size="small"
                :placeholder="v.value || '请输入值'"
                style="flex: 1"
              />
            </div>
          </div>
        </el-form-item>

        <el-form-item label="调度类型">
          <el-select v-model="form.schedule_type" style="width: 100%">
            <el-option label="固定间隔" value="interval" />
            <el-option label="Cron 表达式" value="cron" />
            <el-option label="每天执行" value="daily" />
            <el-option label="仅手动" value="once" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.schedule_type === 'interval'" label="间隔(秒)">
          <el-input-number v-model="form.interval_seconds" :min="10" :max="86400" />
        </el-form-item>
        <el-form-item v-if="form.schedule_type === 'cron'" label="Cron">
          <el-input v-model="form.cron_expression" placeholder="0 */6 * * *" />
        </el-form-item>
        <el-form-item v-if="form.schedule_type === 'daily'" label="执行时间">
          <el-time-picker v-model="form.run_time" format="HH:mm" value-format="HH:mm" placeholder="选择时间" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- Group Management Dialog -->
    <el-dialog v-model="showGroupDialog" title="分组管理" width="500px">
      <div style="margin-bottom: 12px">
        <el-input v-model="newGroupName" placeholder="新分组名称" style="width: 300px; margin-right: 8px" />
        <el-button type="primary" size="small" @click="createGroup">添加分组</el-button>
      </div>
      <el-table :data="groups" size="small" border>
        <el-table-column prop="name" label="分组名" min-width="150" />
        <el-table-column prop="task_count" label="任务数" width="80" />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="deleteGroup(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- Run History Dialog -->
    <TaskRunHistory v-if="historyTaskId" :task-id="historyTaskId" :visible="showHistory" @close="showHistory = false" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTaskStore } from '@/stores/task'
import api from '@/api'
import TaskRunHistory from '@/components/TaskRunHistory.vue'

const { t } = useI18n()
const taskStore = useTaskStore()

const showDialog = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const runningId = ref<number | null>(null)

const showHistory = ref(false)
const historyTaskId = ref<number | null>(null)

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
  try { const res = await api.get('/api/templates?page_size=100'); templates.value = res.data.items } catch {}
}

async function fetchGroups() {
  try { const res = await api.get('/api/task-groups'); groups.value = res.data } catch {}
}

function getTemplateName(id: number) { return templates.value.find((t) => t.id === id)?.name }
function getGroupName(id: number | null) { return groups.value.find((g) => g.id === id)?.name }

function getStatusType(status: string) {
  const m: Record<string, string> = { success: 'success', failed: 'danger', running: 'warning', pending: 'info', paused: 'info' }
  return (m[status] || 'info') as any
}

async function onTemplateChange(templateId: number) {
  const tmpl = templates.value.find((t) => t.id === templateId)
  if (tmpl?.template_data?.requests) {
    // Extract variables from template URLs and headers
    const vars = new Set<string>()
    for (const req of tmpl.template_data.requests) {
      const urlVars = req.url?.match(/\{\{(\w+)\}\}/g) || []
      urlVars.forEach((v: string) => vars.add(v.replace(/\{\{|\}\}/g, '')))
      for (const h of (req.headers || [])) {
        const hVars = h.value?.match(/\{\{(\w+)\}\}/g) || []
        hVars.forEach((v: string) => vars.add(v.replace(/\{\{|\}\}/g, '')))
      }
    }
    templateVariables.value = Array.from(vars).map((key) => ({
      key,
      value: tmpl.variables?.[key] || '',
    }))
    // Initialize form variables
    form.variables = {}
    templateVariables.value.forEach((v) => { form.variables[v.key] = v.value })
  } else {
    templateVariables.value = []
    form.variables = {}
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''; form.description = ''; form.template_id = null; form.group_id = null
  form.schedule_type = 'interval'; form.interval_seconds = 3600; form.cron_expression = ''; form.run_time = '00:00'
  form.variables = {}; templateVariables.value = []
  showDialog.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  form.name = row.name; form.description = row.description || ''; form.template_id = row.template_id
  form.group_id = row.group_id; form.schedule_type = row.schedule_config?.schedule_type || 'interval'
  form.interval_seconds = row.schedule_config?.interval_seconds || 3600
  form.cron_expression = row.schedule_config?.cron_expression || ''
  form.run_time = row.schedule_config?.run_time || '00:00'
  form.variables = { ...(row.variables || {}) }
  onTemplateChange(row.template_id)
  showDialog.value = true
}

function openHistory(row: any) { historyTaskId.value = row.id; showHistory.value = true }

async function save() {
  if (!form.name || !form.template_id) { ElMessage.warning('请填写任务名称并选择模板'); return }
  const scheduleConfig: any = { schedule_type: form.schedule_type }
  if (form.schedule_type === 'interval') scheduleConfig.interval_seconds = form.interval_seconds
  if (form.schedule_type === 'cron') scheduleConfig.cron_expression = form.cron_expression
  if (form.schedule_type === 'daily') scheduleConfig.run_time = form.run_time

  const data: any = {
    name: form.name, description: form.description, template_id: form.template_id!,
    group_id: form.group_id || undefined, schedule_config: scheduleConfig, variables: form.variables,
  }

  saving.value = true
  try {
    if (editingId.value) { await taskStore.updateTask(editingId.value, data) }
    else { await taskStore.createTask(data) }
    showDialog.value = false; ElMessage.success(t('common.success'))
  } catch (err: any) { ElMessage.error(err.response?.data?.detail || '保存失败') }
  finally { saving.value = false }
}

async function runTask(id: number) {
  runningId.value = id
  try { await taskStore.runTask(id); ElMessage.success('任务已触发'); await taskStore.fetchTasks() }
  catch { ElMessage.error('执行失败') }
  finally { runningId.value = null }
}

async function deleteTask(id: number) { await ElMessageBox.confirm('确定删除？'); await taskStore.deleteTask(id); ElMessage.success(t('common.success')) }

// --- Group Management ---
async function createGroup() {
  if (!newGroupName.value.trim()) { ElMessage.warning('请输入分组名称'); return }
  try {
    await api.post('/api/task-groups', { name: newGroupName.value })
    newGroupName.value = ''; await fetchGroups(); ElMessage.success(t('common.success'))
  } catch (err: any) { ElMessage.error(err.response?.data?.detail || '创建失败') }
}

async function deleteGroup(id: number) {
  await ElMessageBox.confirm('确定删除该分组？组内任务将变为未分组。')
  await api.delete(`/api/task-groups/${id}`)
  await fetchGroups(); ElMessage.success(t('common.success'))
}
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
</style>
