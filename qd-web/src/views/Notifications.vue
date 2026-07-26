<template>
  <div class="notifications">
    <div class="page-header">
      <h2>{{ t('notification.title') }}</h2>
      <el-button type="primary" @click="openCreate">{{ t('notification.create') }}</el-button>
    </div>

    <el-table :data="notifications" v-loading="loading" stripe>
      <el-table-column prop="name" label="名称" min-width="120" />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">
          <el-tag size="small">{{ row.notification_type === 'webhook' ? 'Webhook' : '邮件' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
            {{ row.enabled ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="触发条件" width="200">
        <template #default="{ row }">
          <el-tag v-if="row.on_success" size="small" type="success" style="margin-right: 4px">成功</el-tag>
          <el-tag v-if="row.on_failure" size="small" type="danger">失败</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="deleteNotification(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="showDialog" :title="editingId ? '编辑通知' : t('notification.create')" width="550px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="通知名称" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.notification_type" style="width: 100%">
            <el-option label="Webhook" value="webhook" />
            <el-option label="邮件" value="email" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="触发条件">
          <el-checkbox v-model="form.on_success">成功时通知</el-checkbox>
          <el-checkbox v-model="form.on_failure">失败时通知</el-checkbox>
        </el-form-item>

        <!-- Webhook Config -->
        <template v-if="form.notification_type === 'webhook'">
          <el-form-item label="Webhook URL" required>
            <el-input v-model="form.webhook_url" placeholder="https://hooks.example.com/xxx" />
          </el-form-item>
          <el-form-item label="请求方法">
            <el-select v-model="form.webhook_method" style="width: 100%">
              <el-option label="POST" value="POST" />
              <el-option label="GET" value="GET" />
              <el-option label="PUT" value="PUT" />
            </el-select>
          </el-form-item>
        </template>

        <!-- Email Config -->
        <template v-if="form.notification_type === 'email'">
          <el-form-item label="SMTP 服务器" required>
            <el-input v-model="form.smtp_host" placeholder="smtp.example.com" />
          </el-form-item>
          <el-form-item label="SMTP 端口">
            <el-input-number v-model="form.smtp_port" :min="1" :max="65535" />
          </el-form-item>
          <el-form-item label="SMTP 用户">
            <el-input v-model="form.smtp_user" placeholder="user@example.com" />
          </el-form-item>
          <el-form-item label="SMTP 密码">
            <el-input v-model="form.smtp_password" type="password" show-password />
          </el-form-item>
          <el-form-item label="发件人">
            <el-input v-model="form.from_addr" placeholder="sender@example.com" />
          </el-form-item>
          <el-form-item label="收件人" required>
            <el-input v-model="form.to_addr" placeholder="receiver@example.com" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

const { t } = useI18n()

const notifications = ref<any[]>([])
const loading = ref(false)
const showDialog = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)

const form = reactive({
  name: '',
  notification_type: 'webhook',
  enabled: true,
  on_success: true,
  on_failure: true,
  webhook_url: '',
  webhook_method: 'POST',
  smtp_host: '',
  smtp_port: 587,
  smtp_user: '',
  smtp_password: '',
  from_addr: '',
  to_addr: '',
})

onMounted(() => {
  fetchNotifications()
})

async function fetchNotifications() {
  loading.value = true
  try {
    const res = await api.get('/api/notifications')
    notifications.value = res.data
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.notification_type = 'webhook'
  form.enabled = true
  form.on_success = true
  form.on_failure = true
  form.webhook_url = ''
  form.webhook_method = 'POST'
  form.smtp_host = ''
  form.smtp_port = 587
  form.smtp_user = ''
  form.smtp_password = ''
  form.from_addr = ''
  form.to_addr = ''
  showDialog.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  form.name = row.name
  form.notification_type = row.notification_type
  form.enabled = row.enabled
  form.on_success = row.on_success
  form.on_failure = row.on_failure
  const config = row.config || {}
  form.webhook_url = config.url || ''
  form.webhook_method = config.method || 'POST'
  form.smtp_host = config.smtp_host || ''
  form.smtp_port = config.smtp_port || 587
  form.smtp_user = config.smtp_user || ''
  form.smtp_password = config.smtp_password || ''
  form.from_addr = config.from_addr || ''
  form.to_addr = config.to_addr || ''
  showDialog.value = true
}

async function save() {
  if (!form.name) {
    ElMessage.warning('请输入通知名称')
    return
  }

  const config: any = {}
  if (form.notification_type === 'webhook') {
    if (!form.webhook_url) {
      ElMessage.warning('请输入 Webhook URL')
      return
    }
    config.url = form.webhook_url
    config.method = form.webhook_method
  } else {
    if (!form.smtp_host || !form.to_addr) {
      ElMessage.warning('请填写 SMTP 服务器和收件人')
      return
    }
    config.smtp_host = form.smtp_host
    config.smtp_port = form.smtp_port
    config.smtp_user = form.smtp_user
    config.smtp_password = form.smtp_password
    config.from_addr = form.from_addr
    config.to_addr = form.to_addr
  }

  const data = {
    name: form.name,
    notification_type: form.notification_type,
    enabled: form.enabled,
    on_success: form.on_success,
    on_failure: form.on_failure,
    config,
  }

  saving.value = true
  try {
    if (editingId.value) {
      await api.put(`/api/notifications/${editingId.value}`, data)
    } else {
      await api.post('/api/notifications', data)
    }
    showDialog.value = false
    ElMessage.success(t('common.success'))
    await fetchNotifications()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function deleteNotification(id: number) {
  await ElMessageBox.confirm('确定删除该通知？')
  await api.delete(`/api/notifications/${id}`)
  ElMessage.success(t('common.success'))
  await fetchNotifications()
}
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
</style>
