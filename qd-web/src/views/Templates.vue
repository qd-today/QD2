<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { useTemplateStore } from '@/stores/template'
import TemplateEditor from '@/components/TemplateEditor.vue'
import api from '@/api'

const message = useMessage()
const dialog = useDialog()
const templateStore = useTemplateStore()

const showEditor = ref(false)
const editingId = ref<number | null>(null)
const editorData = ref<any>({})
const saving = ref(false)
const editorRef = ref()

onMounted(() => {
  templateStore.fetchTemplates()
})

function openCreate() {
  editingId.value = null
  editorData.value = {}
  showEditor.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  editorData.value = { ...row }
  showEditor.value = true
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
      message.success('已删除')
    },
  })
}
</script>

<template>
  <div>
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-lg font-semibold m-0">模板管理</h2>
      <n-button type="primary" @click="openCreate">新建模板</n-button>
    </div>

    <n-spin :show="templateStore.loading">
      <n-empty
        v-if="templateStore.templates.length === 0 && !templateStore.loading"
        description="暂无模板 — 可从「模板库」安装公共模板，或新建/导入 HAR"
        class="mt-16"
      />
      <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        <n-card
          v-for="row in templateStore.templates"
          :key="row.id"
          size="small"
          class="rounded-lg"
          hoverable
        >
          <div class="flex justify-between items-start gap-2">
            <div class="min-w-0 flex-1">
              <div class="font-medium truncate" :title="row.name">{{ row.name }}</div>
              <div class="text-xs text-gray-400 mt-1 line-clamp-2">
                {{ row.description || '无描述' }}
              </div>
              <div class="mt-2 flex flex-wrap gap-1">
                <n-tag v-for="tag in row.tags" :key="tag" size="tiny" round>{{ tag }}</n-tag>
                <n-tag size="tiny" :type="row.enabled ? 'success' : 'default'" round>
                  {{ row.enabled ? '启用' : '禁用' }}
                </n-tag>
              </div>
            </div>
          </div>
          <template #action>
            <div class="flex gap-1 justify-end">
              <n-button size="tiny" quaternary @click="openEdit(row)">编辑</n-button>
              <n-button size="tiny" quaternary @click="exportTemplate(row.id, 'qd2')">导出</n-button>
              <n-button size="tiny" quaternary @click="exportTemplate(row.id, 'har')">HAR</n-button>
              <n-button size="tiny" quaternary type="error" @click="deleteTemplate(row.id)">
                删除
              </n-button>
            </div>
          </template>
        </n-card>
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
  </div>
</template>
