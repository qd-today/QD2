<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import api from '@/api'

const message = useMessage()
const dialog = useDialog()

const users = ref<any[]>([])
const loading = ref(false)
const settings = ref({ registration_enabled: true, max_tasks_per_user: 0 })
const stats = ref<any>({})

async function load() {
  loading.value = true
  try {
    const [u, s, st] = await Promise.all([
      api.get('/api/admin/users'),
      api.get('/api/admin/settings'),
      api.get('/api/admin/stats'),
    ])
    users.value = u.data
    settings.value = s.data
    stats.value = st.data
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  try {
    const res = await api.put('/api/admin/settings', settings.value)
    settings.value = res.data
    message.success('设置已保存')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  }
}

async function toggleActive(user: any) {
  try {
    await api.put(`/api/admin/users/${user.id}`, { is_active: !user.is_active })
    message.success(user.is_active ? '已禁用' : '已启用')
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '操作失败')
  }
}

async function toggleRole(user: any) {
  try {
    await api.put(`/api/admin/users/${user.id}`, {
      role: user.role === 'admin' ? 'user' : 'admin',
    })
    message.success('角色已更新')
    await load()
  } catch (e: any) {
    message.error(e.response?.data?.detail || '操作失败')
  }
}

function resetPassword(user: any) {
  const pwd = ref('')
  dialog.create({
    title: `重置「${user.username}」的密码`,
    content: () =>
      h(NInput, {
        value: pwd.value,
        type: 'password',
        placeholder: '新密码 (至少6位)',
        'onUpdate:value': (v: string) => (pwd.value = v),
      }),
    positiveText: '重置',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.post(`/api/admin/users/${user.id}/reset-password`, { new_password: pwd.value })
        message.success('密码已重置')
      } catch (e: any) {
        message.error(e.response?.data?.detail || '重置失败')
        return false
      }
    },
  })
}

function removeUser(user: any) {
  dialog.error({
    title: '删除用户',
    content: `确定删除用户「${user.username}」？其全部模板/任务/记录将被一并删除，不可恢复！`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.delete(`/api/admin/users/${user.id}`)
        message.success('用户已删除')
        await load()
      } catch (e: any) {
        message.error(e.response?.data?.detail || '删除失败')
      }
    },
  })
}

import { h } from 'vue'
import { NInput } from 'naive-ui'

onMounted(load)
</script>

<template>
  <div>
    <div class="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-5">
      <n-card size="small" class="rounded-lg text-center">
        <div class="text-2xl font-bold">{{ stats.users ?? '-' }}</div>
        <div class="text-xs text-gray-400">用户</div>
      </n-card>
      <n-card size="small" class="rounded-lg text-center">
        <div class="text-2xl font-bold">{{ stats.tasks ?? '-' }}</div>
        <div class="text-xs text-gray-400">任务</div>
      </n-card>
      <n-card size="small" class="rounded-lg text-center">
        <div class="text-2xl font-bold">{{ stats.templates ?? '-' }}</div>
        <div class="text-xs text-gray-400">模板</div>
      </n-card>
      <n-card size="small" class="rounded-lg text-center">
        <div class="text-2xl font-bold">{{ stats.runs ?? '-' }}</div>
        <div class="text-xs text-gray-400">执行次数</div>
      </n-card>
      <n-card size="small" class="rounded-lg text-center">
        <div class="text-2xl font-bold text-red-500">{{ stats.failed_runs ?? '-' }}</div>
        <div class="text-xs text-gray-400">失败次数</div>
      </n-card>
    </div>

    <n-card title="系统设置" size="small" class="rounded-xl mb-5">
      <div class="flex flex-wrap items-center gap-6">
        <div class="flex items-center gap-2">
          <span class="text-sm">开放注册</span>
          <n-switch v-model:value="settings.registration_enabled" />
        </div>
        <div class="flex items-center gap-2">
          <span class="text-sm">每用户任务上限 (0=不限)</span>
          <n-input-number v-model:value="settings.max_tasks_per_user" :min="0" class="w-28" />
        </div>
        <n-button type="primary" size="small" @click="saveSettings">保存设置</n-button>
      </div>
    </n-card>

    <n-card title="用户管理" size="small" class="rounded-xl" :loading="loading">
      <n-table :bordered="false" :single-line="false" size="small">
        <thead>
          <tr>
            <th>ID</th>
            <th>用户名</th>
            <th>邮箱</th>
            <th>角色</th>
            <th>状态</th>
            <th>任务</th>
            <th>模板</th>
            <th>最后登录</th>
            <th class="!text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td>{{ u.id }}</td>
            <td class="font-medium">{{ u.username }}</td>
            <td class="text-gray-400">{{ u.email || '-' }}</td>
            <td>
              <n-tag :type="u.role === 'admin' ? 'warning' : 'default'" size="small">
                {{ u.role === 'admin' ? '管理员' : '用户' }}
              </n-tag>
            </td>
            <td>
              <n-tag :type="u.is_active ? 'success' : 'error'" size="small">
                {{ u.is_active ? '正常' : '禁用' }}
              </n-tag>
            </td>
            <td>{{ u.task_count }}</td>
            <td>{{ u.template_count }}</td>
            <td class="text-gray-400 text-xs">
              {{ u.last_login ? new Date(u.last_login + 'Z').toLocaleString() : '从未' }}
            </td>
            <td class="!text-right whitespace-nowrap">
              <n-button size="tiny" quaternary @click="toggleRole(u)">
                {{ u.role === 'admin' ? '降为用户' : '升为管理员' }}
              </n-button>
              <n-button size="tiny" quaternary @click="resetPassword(u)">重置密码</n-button>
              <n-button size="tiny" quaternary :type="u.is_active ? 'warning' : 'success'" @click="toggleActive(u)">
                {{ u.is_active ? '禁用' : '启用' }}
              </n-button>
              <n-button size="tiny" quaternary type="error" @click="removeUser(u)">删除</n-button>
            </td>
          </tr>
        </tbody>
      </n-table>
    </n-card>
  </div>
</template>
