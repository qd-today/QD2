<template>
  <div class="templates">
    <div class="page-header">
      <h2>{{ t('template.title') }}</h2>
      <el-button type="primary" @click="openCreate">
        {{ t('template.create') }}
      </el-button>
    </div>

    <el-table :data="templateStore.templates" v-loading="templateStore.loading" stripe>
      <el-table-column prop="name" :label="t('template.name')" min-width="150" />
      <el-table-column prop="description" :label="t('template.description')" min-width="200" show-overflow-tooltip />
      <el-table-column prop="tags" :label="t('template.tags')" width="200">
        <template #default="{ row }">
          <el-tag v-for="tag in row.tags" :key="tag" size="small" style="margin-right: 4px">
            {{ tag }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="enabled" :label="t('template.enabled')" width="80">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
            {{ row.enabled ? '✓' : '✗' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="run_count" :label="t('template.runCount')" width="80" />
      <el-table-column :label="t('template.actions')" width="280" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-dropdown trigger="click" style="margin: 0 4px">
            <el-button size="small">导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="exportTemplate(row.id, 'qd2')">QD2 格式</el-dropdown-item>
                <el-dropdown-item @click="exportTemplate(row.id, 'har')">HAR 格式</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button size="small" type="danger" @click="deleteTemplate(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Create/Edit Dialog -->
    <el-dialog
      v-model="showEditor"
      :title="editingId ? '编辑模板' : t('template.create')"
      width="900px"
      top="5vh"
      destroy-on-close
    >
      <TemplateEditor ref="editorRef" :initial-data="editorData" />
      <template #footer>
        <el-button @click="showEditor = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useTemplateStore } from '@/stores/template'
import TemplateEditor from '@/components/TemplateEditor.vue'
import api from '@/api'

const { t } = useI18n()
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
    ElMessage.success('导出成功')
  } catch (err: any) {
    ElMessage.error('导出失败')
  }
}

async function save() {
  const data = editorRef.value?.getData()
  if (!data) return

  if (!data.name) {
    ElMessage.warning('请输入模板名称')
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
    ElMessage.success(t('common.success'))
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

async function deleteTemplate(id: number) {
  await ElMessageBox.confirm('确定删除该模板？')
  await templateStore.deleteTemplate(id)
  ElMessage.success(t('common.success'))
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
