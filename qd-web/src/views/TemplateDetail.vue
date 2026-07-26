<template>
  <div class="template-detail" v-loading="loading">
    <div class="page-header">
      <div>
        <el-button @click="router.push('/templates')" style="margin-right: 8px">← 返回</el-button>
        <span style="font-size: 18px; font-weight: bold">模板详情 #{{ $route.params.id }}</span>
      </div>
      <div>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </div>
    </div>

    <TemplateEditor v-if="templateData" ref="editorRef" :initial-data="templateData" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api'
import TemplateEditor from '@/components/TemplateEditor.vue'

const route = useRoute()
const router = useRouter()
const editorRef = ref()

const loading = ref(true)
const saving = ref(false)
const templateData = ref<any>(null)

onMounted(async () => {
  try {
    const id = route.params.id
    const response = await api.get(`/api/templates/${id}`)
    templateData.value = response.data
  } catch (err: any) {
    ElMessage.error('加载模板失败')
    router.push('/templates')
  } finally {
    loading.value = false
  }
})

async function save() {
  const data = editorRef.value?.getData()
  if (!data) return

  if (!data.name) {
    ElMessage.warning('请输入模板名称')
    return
  }

  saving.value = true
  try {
    await api.put(`/api/templates/${route.params.id}`, data)
    ElMessage.success('保存成功')
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
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
