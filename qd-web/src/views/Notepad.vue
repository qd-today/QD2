<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import api from '@/api'

const message = useMessage()
const content = ref('')
const notepadId = ref<number | null>(null)
const loading = ref(true)
const saving = ref(false)

onMounted(async () => {
  try {
    const res = await api.get('/api/notepad')
    const first = Array.isArray(res.data) ? res.data[0] : res.data
    if (first) {
      notepadId.value = first.id
      content.value = first.content || ''
    }
  } catch {
    // notepad may be empty
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  try {
    if (notepadId.value === null) {
      const res = await api.post('/api/notepad', { title: '记事本', content: content.value })
      notepadId.value = res.data.id
    } else {
      await api.put(`/api/notepad/${notepadId.value}`, { content: content.value })
    }
    message.success('已保存')
  } catch (e: any) {
    message.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="h-full flex flex-col">
    <div class="flex justify-between items-center mb-4">
      <h2 class="text-lg font-semibold m-0">记事本</h2>
      <n-button type="primary" :loading="saving" @click="save">保存</n-button>
    </div>
    <n-spin :show="loading" class="flex-1">
      <n-input
        v-model:value="content"
        type="textarea"
        placeholder="记录 Cookie、Token、备忘等任意内容…"
        class="h-full font-mono"
        :autosize="{ minRows: 20 }"
      />
    </n-spin>
  </div>
</template>
