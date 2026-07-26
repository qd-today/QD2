<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import api from '@/api'
import TemplateEditor from '@/components/TemplateEditor.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const editorRef = ref()

const loading = ref(true)
const saving = ref(false)
const templateData = ref<any>(null)

onMounted(async () => {
  try {
    const id = route.params.id
    const response = await api.get(`/api/templates/${id}`)
    templateData.value = response.data
  } catch {
    message.error('加载模板失败')
    router.push('/templates')
  } finally {
    loading.value = false
  }
})

async function save() {
  const data = editorRef.value?.getData()
  if (!data) return
  if (!data.name) {
    message.warning('请输入模板名称')
    return
  }
  saving.value = true
  try {
    await api.put(`/api/templates/${route.params.id}`, data)
    message.success('保存成功')
  } catch (err: any) {
    message.error(err.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <n-spin :show="loading">
    <div class="flex justify-between items-center mb-4">
      <div class="flex items-center gap-2">
        <n-button size="small" @click="router.push('/templates')">← 返回</n-button>
        <span class="text-lg font-semibold">模板详情 #{{ route.params.id }}</span>
      </div>
      <n-button type="primary" :loading="saving" @click="save">保存</n-button>
    </div>
    <TemplateEditor v-if="templateData" ref="editorRef" :initial-data="templateData" />
  </n-spin>
</template>
