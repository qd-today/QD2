<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import api from '@/api'

const message = useMessage()
const content = ref('')
const loading = ref(true)
const saving = ref(false)

onMounted(async () => {
  try {
    const res = await api.get('/api/notepad')
    content.value = res.data.content || ''
  } catch {
    // notepad may be empty
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  try {
    await api.put('/api/notepad', { content: content.value })
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
