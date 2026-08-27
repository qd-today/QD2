<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArchiveOutline,
  CloudDownloadOutline,
  CloudUploadOutline,
  ServerOutline,
} from '@vicons/ionicons5'
import { useDialog, useMessage } from 'naive-ui'
import api from '@/api'
import { useAuthStore } from '@/stores/auth'

interface BackupPreview {
  format: string
  version: number
  source_username: string
  created_at: string
  counts: Record<string, number>
  warnings: string[]
}

interface ImportResult {
  mode: string
  counts: Record<string, number>
  warnings: string[]
}

interface V1Preview {
  templates: number
  public_templates: number
  users: number
  tasks: number
  task_groups: number
  notifications: number
  notepads: number
  decryptable: boolean
  detail: string
}

interface V1Result {
  templates_imported: number
  tasks_imported: number
  task_groups_imported: number
  users_imported: number
  notifications_imported: number
  notepads_imported: number
  errors: string[]
}

interface DatabasePreview {
  users: number
  templates: number
  tasks: number
  task_runs: number
  integrity: string
}

const message = useMessage()
const dialog = useDialog()
const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin)

const sectionLabels: Record<string, string> = {
  templates: '模板',
  task_groups: '任务分组',
  tasks: '任务',
  task_runs: '运行记录',
  notifications: '通知配置',
  notepads: '记事本',
  template_sources: '模板源',
}

const exportingPersonal = ref(false)
const personalInput = ref<HTMLInputElement | null>(null)
const personalFile = ref<File | null>(null)
const personalPreview = ref<BackupPreview | null>(null)
const personalResult = ref<ImportResult | null>(null)
const personalPreviewing = ref(false)
const personalImporting = ref(false)
const personalMode = ref<'merge' | 'replace'>('merge')

const v1Input = ref<HTMLInputElement | null>(null)
const v1File = ref<File | null>(null)
const v1AesKey = ref('binux')
const v1Preview = ref<V1Preview | null>(null)
const v1Result = ref<V1Result | null>(null)
const v1Previewing = ref(false)
const v1Importing = ref(false)
const exportingDatabase = ref(false)
const databaseInput = ref<HTMLInputElement | null>(null)
const databaseFile = ref<File | null>(null)
const databasePreview = ref<DatabasePreview | null>(null)
const databasePreviewing = ref(false)
const databaseRestoring = ref(false)
const databaseRestoreStaged = ref(false)

function responseFilename(disposition: string | undefined, fallback: string) {
  if (!disposition) return fallback
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  if (encoded) return decodeURIComponent(encoded)
  return disposition.match(/filename="?([^";]+)"?/i)?.[1] || fallback
}

async function download(endpoint: string, fallback: string) {
  const response = await api.get(endpoint, { responseType: 'blob', timeout: 120_000 })
  const url = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = responseFilename(response.headers['content-disposition'], fallback)
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

async function exportPersonal() {
  exportingPersonal.value = true
  try {
    await download('/api/data/export', 'qd2-user-backup.json')
    message.success('个人数据备份已生成')
  } catch (error: any) {
    message.error(error.response?.data?.detail || '个人数据备份失败')
  } finally {
    exportingPersonal.value = false
  }
}

function choosePersonalFile() {
  personalInput.value?.click()
}

function handlePersonalFile(event: Event) {
  personalFile.value = (event.target as HTMLInputElement).files?.[0] || null
  personalPreview.value = null
  personalResult.value = null
}

function personalFormData() {
  const form = new FormData()
  if (personalFile.value) form.append('file', personalFile.value)
  return form
}

async function previewPersonal() {
  if (!personalFile.value) return
  personalPreviewing.value = true
  try {
    const response = await api.post('/api/data/import/preview', personalFormData(), {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    })
    personalPreview.value = response.data
  } catch (error: any) {
    personalPreview.value = null
    message.error(error.response?.data?.detail || '备份文件预览失败')
  } finally {
    personalPreviewing.value = false
  }
}

async function runPersonalImport() {
  if (!personalFile.value || !personalPreview.value) return
  personalImporting.value = true
  try {
    const form = personalFormData()
    form.append('mode', personalMode.value)
    const response = await api.post('/api/data/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    })
    personalResult.value = response.data
    message.success(personalMode.value === 'replace' ? '个人数据已替换' : '个人数据已合并')
  } catch (error: any) {
    message.error(error.response?.data?.detail || '个人数据导入失败')
  } finally {
    personalImporting.value = false
  }
}

function importPersonal() {
  if (personalMode.value !== 'replace') {
    void runPersonalImport()
    return
  }
  dialog.warning({
    title: '替换个人数据',
    content: '将删除当前账号已有的模板、任务、运行记录、通知配置和记事本，再导入备份内容。',
    positiveText: '确认替换',
    negativeText: '取消',
    onPositiveClick: runPersonalImport,
  })
}

function chooseV1File() {
  v1Input.value?.click()
}

function handleV1File(event: Event) {
  v1File.value = (event.target as HTMLInputElement).files?.[0] || null
  v1Preview.value = null
  v1Result.value = null
}

function v1FormData() {
  const form = new FormData()
  if (v1File.value) form.append('file', v1File.value)
  form.append('aes_key', v1AesKey.value)
  return form
}

async function previewV1() {
  if (!v1File.value) return
  v1Previewing.value = true
  try {
    const response = await api.post('/api/migrate/preview', v1FormData(), {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    })
    v1Preview.value = response.data
  } catch (error: any) {
    v1Preview.value = null
    message.error(error.response?.data?.detail || 'QD v1 数据库预览失败')
  } finally {
    v1Previewing.value = false
  }
}

async function importV1() {
  if (!v1File.value || !v1Preview.value?.decryptable) return
  v1Importing.value = true
  try {
    const response = await api.post('/api/migrate/import', v1FormData(), {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180_000,
    })
    v1Result.value = response.data
    message.success('QD v1 数据迁移完成')
  } catch (error: any) {
    message.error(error.response?.data?.detail || 'QD v1 数据迁移失败')
  } finally {
    v1Importing.value = false
  }
}

async function exportDatabase() {
  exportingDatabase.value = true
  try {
    await download('/api/data/admin/database', 'qd2-database.db')
    message.success('完整数据库快照已生成')
  } catch (error: any) {
    message.error(error.response?.data?.detail || '完整数据库备份失败')
  } finally {
    exportingDatabase.value = false
  }
}

function chooseDatabaseFile() {
  databaseInput.value?.click()
}

function handleDatabaseFile(event: Event) {
  databaseFile.value = (event.target as HTMLInputElement).files?.[0] || null
  databasePreview.value = null
  databaseRestoreStaged.value = false
}

function databaseFormData() {
  const form = new FormData()
  if (databaseFile.value) form.append('file', databaseFile.value)
  return form
}

async function previewDatabaseRestore() {
  if (!databaseFile.value) return
  databasePreviewing.value = true
  try {
    const response = await api.post('/api/data/admin/database/preview', databaseFormData(), {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180_000,
    })
    databasePreview.value = response.data
  } catch (error: any) {
    databasePreview.value = null
    message.error(error.response?.data?.detail || '数据库备份预览失败')
  } finally {
    databasePreviewing.value = false
  }
}

async function stageDatabaseRestore() {
  if (!databaseFile.value || !databasePreview.value) return
  databaseRestoring.value = true
  try {
    const form = databaseFormData()
    form.append('confirmation', 'RESTORE')
    await api.post('/api/data/admin/database/restore', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180_000,
    })
    databaseRestoreStaged.value = true
    message.success('数据库恢复已安排，请重启后端服务')
  } catch (error: any) {
    message.error(error.response?.data?.detail || '安排数据库恢复失败')
  } finally {
    databaseRestoring.value = false
  }
}

function restoreDatabase() {
  dialog.error({
    title: '恢复完整数据库',
    content: '下次启动后端时将替换当前全部用户和业务数据。系统会保留一份恢复前数据库副本。',
    positiveText: '安排恢复',
    negativeText: '取消',
    onPositiveClick: stageDatabaseRestore,
  })
}
</script>

<template>
  <div class="mx-auto max-w-6xl">
    <div class="mb-4 flex items-center gap-2">
      <n-icon size="22"><ArchiveOutline /></n-icon>
      <h1 class="text-lg font-semibold">数据管理</h1>
    </div>

    <n-tabs type="line" animated>
      <n-tab-pane name="personal" tab="我的数据">
        <section class="border-b border-gray-200 py-5 first:pt-2 dark:border-gray-700">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 class="text-base font-medium">导出个人数据</h2>
              <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">不包含密码、角色和系统设置。</p>
            </div>
            <n-button type="primary" :loading="exportingPersonal" @click="exportPersonal">
              <template #icon><n-icon><CloudDownloadOutline /></n-icon></template>
              下载备份
            </n-button>
          </div>
        </section>

        <section class="py-5">
          <h2 class="text-base font-medium">导入个人数据</h2>
          <input ref="personalInput" type="file" accept=".json,application/json" class="hidden" @change="handlePersonalFile">
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <n-button secondary @click="choosePersonalFile">
              <template #icon><n-icon><CloudUploadOutline /></n-icon></template>
              选择备份文件
            </n-button>
            <span class="max-w-full truncate text-sm text-gray-500 dark:text-gray-400">
              {{ personalFile?.name || '未选择文件' }}
            </span>
            <n-button :disabled="!personalFile" :loading="personalPreviewing" @click="previewPersonal">预览</n-button>
          </div>

          <div v-if="personalPreview" class="mt-4 border-t border-gray-200 pt-4 dark:border-gray-700">
            <div class="grid grid-cols-2 gap-x-5 gap-y-2 text-sm sm:grid-cols-4">
              <div v-for="(count, section) in personalPreview.counts" :key="section" class="flex justify-between gap-3 border-b border-gray-100 py-1 dark:border-gray-800">
                <span class="text-gray-500 dark:text-gray-400">{{ sectionLabels[section] || section }}</span>
                <span class="font-medium">{{ count }}</span>
              </div>
            </div>
            <n-alert v-for="warning in personalPreview.warnings" :key="warning" type="warning" class="mt-3">
              {{ warning }}
            </n-alert>
            <div class="mt-4 flex flex-wrap items-center gap-3">
              <n-radio-group v-model:value="personalMode" size="small">
                <n-radio-button value="merge">合并</n-radio-button>
                <n-radio-button value="replace">替换</n-radio-button>
              </n-radio-group>
              <n-button type="primary" :loading="personalImporting" @click="importPersonal">开始导入</n-button>
            </div>
          </div>

          <n-alert v-if="personalResult" type="success" class="mt-4">
            已导入 {{ Object.values(personalResult.counts).reduce((total, count) => total + count, 0) }} 条数据。
            <span v-if="personalResult.warnings.length">{{ personalResult.warnings.join('；') }}</span>
          </n-alert>
        </section>
      </n-tab-pane>

      <n-tab-pane v-if="isAdmin" name="v1" tab="QD v1 迁移">
        <section class="py-2">
          <n-alert type="warning" class="mb-4">
            v1 用户将以禁用状态导入，原密码不会迁移。完成后请在用户管理中启用账号并重置密码。
          </n-alert>
          <input ref="v1Input" type="file" accept=".db,application/vnd.sqlite3" class="hidden" @change="handleV1File">
          <div class="grid gap-3 sm:grid-cols-[auto_minmax(14rem,1fr)_minmax(12rem,20rem)_auto] sm:items-center">
            <n-button secondary @click="chooseV1File">
              <template #icon><n-icon><CloudUploadOutline /></n-icon></template>
              选择 database.db
            </n-button>
            <span class="truncate text-sm text-gray-500 dark:text-gray-400">{{ v1File?.name || '未选择文件' }}</span>
            <n-input v-model:value="v1AesKey" type="password" show-password-on="click" placeholder="AES_KEY" />
            <n-button :disabled="!v1File" :loading="v1Previewing" @click="previewV1">预览</n-button>
          </div>

          <div v-if="v1Preview" class="mt-5 border-t border-gray-200 pt-4 dark:border-gray-700">
            <div class="flex flex-wrap gap-x-8 gap-y-2 text-sm">
              <span>用户 <strong>{{ v1Preview.users }}</strong></span>
              <span>模板 <strong>{{ v1Preview.templates }}</strong></span>
              <span>公共模板副本 <strong>{{ v1Preview.public_templates }}</strong></span>
              <span>任务 <strong>{{ v1Preview.tasks }}</strong></span>
              <span>任务分组 <strong>{{ v1Preview.task_groups }}</strong></span>
              <span>通知渠道 <strong>{{ v1Preview.notifications }}</strong></span>
              <span>记事本 <strong>{{ v1Preview.notepads }}</strong></span>
              <n-tag :type="v1Preview.decryptable ? 'success' : 'error'" size="small">
                {{ v1Preview.decryptable ? '可解密' : '无法解密' }}
              </n-tag>
            </div>
            <p v-if="v1Preview.detail" class="mt-2 text-sm text-gray-500 dark:text-gray-400">{{ v1Preview.detail }}</p>
            <n-button class="mt-4" type="primary" :disabled="!v1Preview.decryptable" :loading="v1Importing" @click="importV1">
              开始迁移
            </n-button>
          </div>

          <n-alert v-if="v1Result" :type="v1Result.errors.length ? 'warning' : 'success'" class="mt-4">
            已导入 {{ v1Result.users_imported }} 个用户、{{ v1Result.templates_imported }} 个模板、{{ v1Result.tasks_imported }} 个任务、{{ v1Result.task_groups_imported }} 个任务分组、{{ v1Result.notifications_imported }} 个通知渠道、{{ v1Result.notepads_imported }} 条记事本。
            <div v-for="error in v1Result.errors" :key="error" class="mt-1 text-xs">{{ error }}</div>
          </n-alert>
        </section>
      </n-tab-pane>

      <n-tab-pane v-if="isAdmin" name="system" tab="系统备份">
        <section class="py-2">
          <n-alert type="warning" class="mb-4">
            完整数据库包含全部用户的密码哈希、Cookie、通知令牌及其他敏感配置。
          </n-alert>
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 py-4 dark:border-gray-700">
            <div>
              <h2 class="text-base font-medium">SQLite 完整快照</h2>
              <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">使用 SQLite Backup API 生成运行时一致性副本。</p>
            </div>
            <n-button type="primary" :loading="exportingDatabase" @click="exportDatabase">
              <template #icon><n-icon><ServerOutline /></n-icon></template>
              下载 database.db
            </n-button>
          </div>

          <div class="py-5">
            <h2 class="text-base font-medium">恢复 SQLite 数据库</h2>
            <input ref="databaseInput" type="file" accept=".db,application/vnd.sqlite3" class="hidden" @change="handleDatabaseFile">
            <div class="mt-3 flex flex-wrap items-center gap-2">
              <n-button secondary @click="chooseDatabaseFile">
                <template #icon><n-icon><CloudUploadOutline /></n-icon></template>
                选择数据库备份
              </n-button>
              <span class="max-w-full truncate text-sm text-gray-500 dark:text-gray-400">
                {{ databaseFile?.name || '未选择文件' }}
              </span>
              <n-button :disabled="!databaseFile" :loading="databasePreviewing" @click="previewDatabaseRestore">预览</n-button>
            </div>

            <div v-if="databasePreview" class="mt-4 border-t border-gray-200 pt-4 dark:border-gray-700">
              <div class="flex flex-wrap gap-x-8 gap-y-2 text-sm">
                <span>用户 <strong>{{ databasePreview.users }}</strong></span>
                <span>模板 <strong>{{ databasePreview.templates }}</strong></span>
                <span>任务 <strong>{{ databasePreview.tasks }}</strong></span>
                <span>运行记录 <strong>{{ databasePreview.task_runs }}</strong></span>
                <n-tag type="success" size="small">完整性正常</n-tag>
              </div>
              <n-button class="mt-4" type="error" :loading="databaseRestoring" @click="restoreDatabase">
                安排完整恢复
              </n-button>
            </div>

            <n-alert v-if="databaseRestoreStaged" type="warning" class="mt-4">
              恢复文件已暂存。请停止并重新启动后端服务；启动时会保留恢复前数据库副本。
            </n-alert>
          </div>
        </section>
      </n-tab-pane>
    </n-tabs>
  </div>
</template>
