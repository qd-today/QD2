<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import api from '@/api'

const message = useMessage()
const dialog = useDialog()

const notifications = ref<any[]>([])
const channels = ref<Record<string, { label: string; fields: string[] }>>({})
const loading = ref(false)
const showDialog = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const testingId = ref<number | null>(null)

const form = reactive({
  name: '',
  notification_type: 'webhook',
  enabled: true,
  on_success: true,
  on_failure: true,
  config: {} as Record<string, any>,
})

// 字段中文标签
const FIELD_LABELS: Record<string, string> = {
  url: 'URL',
  method: '请求方法',
  headers: '附加 Headers (JSON)',
  smtp_host: 'SMTP 服务器',
  smtp_port: 'SMTP 端口',
  smtp_user: 'SMTP 用户',
  smtp_password: 'SMTP 密码',
  from_addr: '发件人',
  to_addr: '收件人',
  use_tls: '使用 TLS',
  server: '服务器地址',
  device_key: 'Device Key',
  group: '分组 (可选)',
  sound: '铃声 (可选)',
  sendkey: 'SendKey',
  bot_token: 'Bot Token',
  chat_id: 'Chat ID',
  api_host: 'API 地址 (可选)',
  pushkey: 'PushKey',
  token: 'Token',
  priority: '优先级',
  access_token: 'Access Token',
  secret: '加签密钥 (可选)',
  key: 'Key',
  corp_id: '企业 ID (CorpID)',
  corp_secret: '应用 Secret',
  agent_id: '应用 AgentId',
  touser: '接收成员账号',
}

onMounted(async () => {
  await Promise.all([fetchNotifications(), fetchChannels()])
})

async function fetchChannels() {
  try {
    const res = await api.get('/api/notifications/channels')
    channels.value = res.data
  } catch {
    message.error('通知渠道类型加载失败')
  }
}

async function fetchNotifications() {
  loading.value = true
  try {
    const res = await api.get('/api/notifications')
    notifications.value = res.data
  } catch {
    message.error('通知渠道加载失败')
  } finally {
    loading.value = false
  }
}

function channelLabel(type: string): string {
  return channels.value[type]?.label || type
}

function openCreate() {
  editingId.value = null
  form.name = ''
  form.notification_type = 'webhook'
  form.enabled = true
  form.on_success = true
  form.on_failure = true
  form.config = {}
  showDialog.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  form.name = row.name
  form.notification_type = row.notification_type
  form.enabled = row.enabled
  form.on_success = row.on_success
  form.on_failure = row.on_failure
  form.config = { ...(row.config || {}) }
  showDialog.value = true
}

async function save() {
  if (!form.name) {
    message.warning('请输入通知名称')
    return
  }
  const data = {
    name: form.name,
    notification_type: form.notification_type,
    enabled: form.enabled,
    on_success: form.on_success,
    on_failure: form.on_failure,
    config: form.config,
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api.put(`/api/notifications/${editingId.value}`, data)
    } else {
      await api.post('/api/notifications', data)
    }
    showDialog.value = false
    message.success('保存成功')
    await fetchNotifications()
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function testSend(row: any) {
  testingId.value = row.id
  try {
    const res = await api.post(`/api/notifications/${row.id}/test`)
    if (res.data.sent) message.success('测试消息已发送，请检查接收端')
    else message.error('发送失败，请检查配置')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '发送失败')
  } finally {
    testingId.value = null
  }
}

function deleteNotification(id: number) {
  dialog.warning({
    title: '删除通知',
    content: '确定删除该通知渠道？',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      await api.delete(`/api/notifications/${id}`)
      message.success('已删除')
      await fetchNotifications()
    },
  })
}
</script>

<template>
  <div>
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-lg font-semibold m-0">通知渠道</h2>
      <n-button type="primary" @click="openCreate">添加渠道</n-button>
    </div>

    <n-spin :show="loading">
      <n-empty
        v-if="notifications.length === 0 && !loading"
        description="暂无通知渠道 — 支持 Bark / Server酱 / Telegram / 钉钉 / 企业微信机器人与 Pusher / PushDeer / Gotify / Webhook / 邮件"
        class="mt-16"
      />
      <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        <n-card v-for="row in notifications" :key="row.id" size="small" class="rounded-lg" hoverable>
          <div class="flex justify-between items-center">
            <div>
              <div class="font-medium">{{ row.name }}</div>
              <div class="mt-1 flex gap-1">
                <n-tag size="tiny" type="info" round>{{ channelLabel(row.notification_type) }}</n-tag>
                <n-tag size="tiny" :type="row.enabled ? 'success' : 'default'" round>
                  {{ row.enabled ? '启用' : '禁用' }}
                </n-tag>
                <n-tag v-if="row.on_success" size="tiny" type="success" round>成功</n-tag>
                <n-tag v-if="row.on_failure" size="tiny" type="error" round>失败</n-tag>
              </div>
            </div>
          </div>
          <template #action>
            <div class="flex gap-1 justify-end">
              <n-button
                size="tiny"
                quaternary
                type="info"
                :loading="testingId === row.id"
                @click="testSend(row)"
              >
                测试
              </n-button>
              <n-button size="tiny" quaternary @click="openEdit(row)">编辑</n-button>
              <n-button size="tiny" quaternary type="error" @click="deleteNotification(row.id)">
                删除
              </n-button>
            </div>
          </template>
        </n-card>
      </div>
    </n-spin>

    <n-modal
      v-model:show="showDialog"
      preset="card"
      :title="editingId ? '编辑通知' : '添加通知渠道'"
      class="max-w-xl"
      :style="{ width: '92vw' }"
    >
      <n-form label-placement="left" label-width="120">
        <n-form-item label="名称" required>
          <n-input v-model:value="form.name" placeholder="通知名称" />
        </n-form-item>
        <n-form-item label="渠道类型">
          <n-select
            v-model:value="form.notification_type"
            :options="Object.entries(channels).map(([k, v]) => ({ label: v.label, value: k }))"
          />
        </n-form-item>
        <n-form-item label="启用">
          <n-switch v-model:value="form.enabled" />
        </n-form-item>
        <n-form-item label="触发条件">
          <n-checkbox v-model:checked="form.on_success">成功时</n-checkbox>
          <n-checkbox v-model:checked="form.on_failure" class="ml-3">失败时</n-checkbox>
        </n-form-item>

        <n-divider title-placement="left" class="!my-2 !text-xs">渠道配置</n-divider>
        <n-form-item
          v-for="field in channels[form.notification_type]?.fields || []"
          :key="field"
          :label="FIELD_LABELS[field] || field"
        >
          <n-switch v-if="field === 'use_tls'" v-model:value="form.config[field]" />
          <n-input-number
            v-else-if="field === 'smtp_port' || field === 'priority' || field === 'agent_id'"
            v-model:value="form.config[field]"
            class="w-full"
          />
          <n-input
            v-else
            v-model:value="form.config[field]"
            :type="field.includes('password') || field.includes('token') || field.includes('key') || field.includes('secret') ? 'password' : 'text'"
            show-password-on="click"
            :placeholder="FIELD_LABELS[field] || field"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="showDialog = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>
