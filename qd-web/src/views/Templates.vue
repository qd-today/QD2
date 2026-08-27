<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { useRouter } from 'vue-router'
import { AddOutline, CloudDownloadOutline } from '@vicons/ionicons5'
import { useTemplateStore } from '@/stores/template'
import TemplateEditor from '@/components/TemplateEditor.vue'
import api from '@/api'

const message = useMessage()
const dialog = useDialog()
const router = useRouter()
const templateStore = useTemplateStore()

const showEditor = ref(false)
const editingId = ref<number | null>(null)
const editorData = ref<any>({})
const saving = ref(false)
const editorRef = ref()
const selectedTemplateIds = ref<number[]>([])
const collapsedTemplateGroups = ref<Record<string, boolean>>({})
const showGroupDialog = ref(false)
const groupTemplateId = ref<number | null>(null)
const groupValue = ref('')
const groupSaving = ref(false)
const publishSavingId = ref<number | null>(null)
const currentPage = ref(1)
const pageSize = ref(20)
const search = ref('')

function templateGroupName(row: any): string {
  const groupTag = (row.tags || []).find((tag: string) => tag.startsWith('group:'))
  return groupTag?.slice(6).trim() || 'None'
}

const templateSections = computed(() => {
  const sections = new Map<string, any[]>()
  for (const row of templateStore.templates) {
    const group = templateGroupName(row)
    if (!sections.has(group)) sections.set(group, [])
    sections.get(group)!.push(row)
  }
  return Array.from(sections, ([name, templates]) => ({ name, templates }))
})

const allTemplatesSelected = computed(
  () => templateStore.templates.length > 0
    && templateStore.templates.every((row) => selectedTemplateIds.value.includes(row.id)),
)

onMounted(() => {
  void loadTemplates()
})

async function loadTemplates() {
  await templateStore.fetchTemplates(currentPage.value, pageSize.value, search.value.trim())
  selectedTemplateIds.value = []
}

async function doSearch() {
  currentPage.value = 1
  await loadTemplates()
}

async function handlePageChange(page: number) {
  currentPage.value = page
  await loadTemplates()
}

async function handlePageSizeChange(size: number) {
  pageSize.value = size
  currentPage.value = 1
  await loadTemplates()
}

function openCreate() {
  editingId.value = null
  editorData.value = {}
  showEditor.value = true
}

function openEdit(row: any) {
  const href = router.resolve({ name: 'TemplateDetail', params: { id: row.id } }).href
  window.open(href, '_blank', 'noopener,noreferrer')
}

function createTask(row: any) {
  router.push({ path: '/tasks', query: { create: '1', template_id: String(row.id) } })
}

function formatDateTime(value?: string | null) {
  if (!value) return '从未'
  const normalized = value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString()
}

function toggleTemplateSelection(id: number, checked: boolean) {
  if (checked && !selectedTemplateIds.value.includes(id)) selectedTemplateIds.value.push(id)
  if (!checked) selectedTemplateIds.value = selectedTemplateIds.value.filter((templateId) => templateId !== id)
}

function toggleAllTemplateSelection(checked: boolean) {
  selectedTemplateIds.value = checked ? templateStore.templates.map((row) => row.id) : []
}

function isTemplateGroupSelected(rows: any[]) {
  return rows.length > 0 && rows.every((row) => selectedTemplateIds.value.includes(row.id))
}

function toggleTemplateGroupSelection(rows: any[], checked: boolean) {
  const ids = new Set(selectedTemplateIds.value)
  for (const row of rows) {
    if (checked) ids.add(row.id)
    else ids.delete(row.id)
  }
  selectedTemplateIds.value = Array.from(ids)
}

function toggleTemplateGroup(name: string) {
  collapsedTemplateGroups.value[name] = !collapsedTemplateGroups.value[name]
}

function openTemplateGroup(row: any) {
  groupTemplateId.value = row.id
  const current = templateGroupName(row)
  groupValue.value = current === 'None' ? '' : current
  showGroupDialog.value = true
}

async function saveTemplateGroup() {
  if (!groupTemplateId.value) return
  const row = templateStore.templates.find((template) => template.id === groupTemplateId.value)
  if (!row) return
  groupSaving.value = true
  try {
    const tags = (row.tags || []).filter((tag: string) => !tag.startsWith('group:'))
    if (groupValue.value.trim()) tags.push(`group:${groupValue.value.trim()}`)
    await templateStore.updateTemplate(row.id, { tags })
    showGroupDialog.value = false
    message.success('模板分组已保存')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '模板分组保存失败')
  } finally {
    groupSaving.value = false
  }
}

async function togglePublish(row: any) {
  const willPublish = !row.is_public
  publishSavingId.value = row.id
  try {
    await templateStore.updateTemplate(row.id, { is_public: willPublish })
    message.success(willPublish ? '模板已发布' : '模板已取消发布')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '发布状态更新失败')
  } finally {
    publishSavingId.value = null
  }
}

async function exportTemplate(id: number, format: string) {
  try {
    const res = await api.get(`/api/templates/${id}/export?format=${format}`, {
      responseType: 'blob',
    })
    const blob = new Blob([res.data])
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `template.${format === 'har' ? 'har' : 'json'}`
    a.click()
    window.URL.revokeObjectURL(url)
    message.success('导出成功')
  } catch {
    message.error('导出失败')
  }
}

async function save() {
  const data = editorRef.value?.getData()
  if (!data) return
  if (!data.name) {
    message.warning('请输入模板名称')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await templateStore.updateTemplate(editingId.value, data)
    } else {
      await templateStore.createTemplate(data)
    }
    showEditor.value = false
    message.success('保存成功')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function deleteTemplate(id: number) {
  dialog.warning({
    title: '删除模板',
    content: '确定删除该模板？',
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      await templateStore.deleteTemplate(id)
      if (templateStore.templates.length === 0 && currentPage.value > 1) currentPage.value--
      await loadTemplates()
      message.success('已删除')
    },
  })
}
</script>

<template>
  <div>
    <div class="flex flex-wrap justify-between items-center gap-2 mb-4">
      <h2 class="text-lg font-semibold m-0">我的模板</h2>
      <div class="flex flex-wrap items-center justify-end gap-2">
        <n-input-group class="!w-72">
          <n-input v-model:value="search" clearable placeholder="搜索模板名称" @keyup.enter="doSearch" />
          <n-button type="primary" ghost @click="doSearch">搜索</n-button>
        </n-input-group>
        <n-button type="primary" @click="openCreate">
          <template #icon><n-icon><AddOutline /></n-icon></template>
          新建模板
        </n-button>
        <n-button @click="router.push('/template-store')">
          <template #icon><n-icon><CloudDownloadOutline /></n-icon></template>
          公共模板
        </n-button>
      </div>
    </div>

    <n-spin :show="templateStore.loading">
      <n-empty
        v-if="templateStore.templates.length === 0 && !templateStore.loading"
        description="暂无模板 — 可从「模板库」安装公共模板，或新建/导入 HAR"
        class="mt-16"
      />
      <div v-else class="overflow-x-auto">
        <n-table :bordered="false" :single-line="false" size="small" class="min-w-[62rem]">
          <thead>
            <tr>
              <th class="w-10">
                <n-checkbox
                  :checked="allTemplatesSelected"
                  :indeterminate="selectedTemplateIds.length > 0 && !allTemplatesSelected"
                  aria-label="选择全部模板"
                  @update:checked="toggleAllTemplateSelection"
                />
              </th>
              <th>模板名称</th>
              <th class="w-48">创建时间</th>
              <th class="w-48">最近修改</th>
              <th class="w-48">最近成功</th>
              <th class="!text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="section in templateSections" :key="section.name">
              <tr class="bg-sky-50 dark:bg-sky-950/40">
                <td colspan="6" class="!py-2">
                  <div class="flex items-center justify-between gap-2">
                    <div class="flex items-center gap-2 font-semibold">
                      <n-checkbox
                        :checked="isTemplateGroupSelected(section.templates)"
                        :indeterminate="section.templates.some((row) => selectedTemplateIds.includes(row.id)) && !isTemplateGroupSelected(section.templates)"
                        :aria-label="`选择${section.name}分组模板`"
                        @update:checked="toggleTemplateGroupSelection(section.templates, $event)"
                      />
                      <span>{{ section.name }} 分组</span>
                    </div>
                    <n-button
                      size="tiny"
                      quaternary
                      :aria-label="`${collapsedTemplateGroups[section.name] ? '展开' : '收起'}${section.name}分组`"
                      @click="toggleTemplateGroup(section.name)"
                    >
                      {{ collapsedTemplateGroups[section.name] ? '展开' : '收起' }}
                    </n-button>
                  </div>
                </td>
              </tr>
              <template v-if="!collapsedTemplateGroups[section.name]">
                <tr v-for="row in section.templates" :key="row.id">
                  <td>
                    <n-checkbox
                      :checked="selectedTemplateIds.includes(row.id)"
                      :aria-label="`选择模板 ${row.name}`"
                      @update:checked="toggleTemplateSelection(row.id, $event)"
                    />
                  </td>
                  <td>
                    <div class="flex items-center gap-1 min-w-0">
                      <n-tag v-if="!row.enabled" size="tiny" type="warning">禁用</n-tag>
                      <span class="font-medium truncate" :title="row.name">{{ row.name }}</span>
                      <span class="text-xs text-gray-400 shrink-0">- {{ templateGroupName(row) }}</span>
                    </div>
                  </td>
                  <td class="text-xs whitespace-nowrap">{{ formatDateTime(row.created_at) }}</td>
                  <td class="text-xs whitespace-nowrap">{{ formatDateTime(row.updated_at) }}</td>
                  <td class="text-xs whitespace-nowrap">{{ formatDateTime(row.last_success_at) }}</td>
                  <td class="!text-right whitespace-nowrap">
                    <n-button size="tiny" quaternary @click="openEdit(row)">编辑</n-button>
                    <n-button size="tiny" quaternary type="error" @click="deleteTemplate(row.id)">删除</n-button>
                    <n-button size="tiny" type="primary" quaternary title="基于此模板新建任务" @click="createTask(row)">新建</n-button>
                    <n-button
                      size="tiny"
                      quaternary
                      :type="row.is_public ? 'warning' : 'success'"
                      :loading="publishSavingId === row.id"
                      @click="togglePublish(row)"
                    >
                      {{ row.is_public ? '取消发布' : '发布' }}
                    </n-button>
                    <n-button size="tiny" quaternary @click="openTemplateGroup(row)">分组</n-button>
                    <n-dropdown
                      trigger="click"
                      :options="[
                        { label: '导出 QD2', key: 'qd2' },
                        { label: '导出 HAR', key: 'har' },
                      ]"
                      @select="(format: string) => exportTemplate(row.id, format)"
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
      <div v-if="templateStore.total > pageSize" class="mt-4 flex justify-end">
        <n-pagination
          :page="currentPage"
          :page-size="pageSize"
          :item-count="templateStore.total"
          :page-sizes="[20, 50, 100]"
          show-size-picker
          @update:page="handlePageChange"
          @update:page-size="handlePageSizeChange"
        />
      </div>
    </n-spin>

    <n-modal
      v-model:show="showEditor"
      preset="card"
      :title="editingId ? '编辑模板' : '新建模板'"
      class="max-w-4xl"
      :style="{ width: '92vw' }"
    >
      <TemplateEditor ref="editorRef" :initial-data="editorData" />
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="showEditor = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="save">保存</n-button>
        </div>
      </template>
    </n-modal>

    <n-modal
      v-model:show="showGroupDialog"
      preset="card"
      title="模板分组"
      class="max-w-md"
      :style="{ width: '92vw' }"
    >
      <n-input v-model:value="groupValue" placeholder="分组名称；留空移到 None 分组" maxlength="100" />
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="showGroupDialog = false">取消</n-button>
          <n-button type="primary" :loading="groupSaving" @click="saveTemplateGroup">保存</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>
