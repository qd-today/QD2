<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import { AddOutline, SaveOutline, TrashOutline } from '@vicons/ionicons5'
import api from '@/api'

interface NotepadEntry {
  id: number
  title: string
  content: string
  category?: string | null
  tags?: string | null
  sort_order: number
  created_at: string
  updated_at: string
}

const dialog = useDialog()
const message = useMessage()
const notes = ref<NotepadEntry[]>([])
const selectedId = ref<number | null>(null)
const title = ref('')
const content = ref('')
const loading = ref(true)
const creating = ref(false)
const saving = ref(false)
const deleting = ref(false)

const selectedNote = computed(() => notes.value.find((note) => note.id === selectedId.value) || null)
const mutating = computed(() => creating.value || saving.value || deleting.value)

function selectNote(note: NotepadEntry) {
  selectedId.value = note.id
  title.value = note.title
  content.value = note.content || ''
}

function formatTime(value: string) {
  const normalized = value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`
  return new Date(normalized).toLocaleString()
}

async function fetchNotes() {
  loading.value = true
  try {
    const response = await api.get('/api/notepad')
    notes.value = response.data
    const current = notes.value.find((note) => note.id === selectedId.value) || notes.value[0]
    if (current) selectNote(current)
  } catch (error: any) {
    message.error(error.response?.data?.detail || '记事本加载失败')
  } finally {
    loading.value = false
  }
}

async function createNote() {
  if (mutating.value) return
  creating.value = true
  try {
    const response = await api.post('/api/notepad', { title: '新记事本', content: '' })
    notes.value.unshift(response.data)
    selectNote(response.data)
    message.success(`已新建记事本 #${response.data.id}`)
  } catch (error: any) {
    message.error(error.response?.data?.detail || '新建失败')
  } finally {
    creating.value = false
  }
}

async function save() {
  if (mutating.value || !selectedId.value) return
  saving.value = true
  try {
    const response = await api.put(`/api/notepad/${selectedId.value}`, {
      title: title.value.trim() || `记事本 #${selectedId.value}`,
      content: content.value,
    })
    notes.value = [response.data, ...notes.value.filter((note) => note.id !== response.data.id)]
    selectNote(response.data)
    message.success(`记事本 #${response.data.id} 已保存`)
  } catch (error: any) {
    message.error(error.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

function deleteNote() {
  if (mutating.value || !selectedNote.value) return
  const note = selectedNote.value
  dialog.warning({
    title: '删除记事本',
    content: `确定删除「${note.title}」(#${note.id})？`,
    positiveText: '删除',
    negativeText: '取消',
    async onPositiveClick() {
      deleting.value = true
      try {
        await api.delete(`/api/notepad/${note.id}`)
        notes.value = notes.value.filter((item) => item.id !== note.id)
        const next = notes.value[0]
        if (next) {
          selectNote(next)
        } else {
          selectedId.value = null
          title.value = ''
          content.value = ''
        }
        message.success(`记事本 #${note.id} 已删除`)
      } catch (error: any) {
        message.error(error.response?.data?.detail || '删除失败')
        return false
      } finally {
        deleting.value = false
      }
    },
  })
}

onMounted(fetchNotes)
</script>

<template>
  <div class="h-full flex flex-col min-h-0">
    <div class="flex flex-wrap justify-between items-center gap-2 mb-4">
      <h2 class="text-lg font-semibold m-0">记事本</h2>
      <div class="flex items-center gap-2">
        <n-button :loading="creating" :disabled="saving" @click="createNote">
          <template #icon><n-icon><AddOutline /></n-icon></template>
          新建
        </n-button>
        <n-button type="error" secondary :disabled="mutating || !selectedNote" @click="deleteNote">
          <template #icon><n-icon><TrashOutline /></n-icon></template>
          删除
        </n-button>
        <n-button type="primary" :loading="saving" :disabled="creating || !selectedNote" @click="save">
          <template #icon><n-icon><SaveOutline /></n-icon></template>
          保存
        </n-button>
      </div>
    </div>

    <n-spin :show="loading" class="flex-1 min-h-0">
      <div class="grid grid-cols-1 md:grid-cols-[16rem_minmax(0,1fr)] min-h-[34rem] border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        <aside class="border-b md:border-b-0 md:border-r border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 min-h-0">
          <div class="px-3 py-2 text-xs font-medium text-gray-500 border-b border-gray-200 dark:border-gray-700">
            记事本列表
          </div>
          <div class="max-h-48 md:max-h-[calc(34rem-2.25rem)] overflow-auto p-2 space-y-1">
            <button
              v-for="note in notes"
              :key="note.id"
              type="button"
              class="w-full text-left px-3 py-2 rounded-md transition-colors"
              :class="note.id === selectedId
                ? 'bg-indigo-100 text-indigo-900 dark:bg-indigo-950 dark:text-indigo-100'
                : 'hover:bg-gray-100 dark:hover:bg-gray-800'"
              @click="selectNote(note)"
            >
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-xs font-mono text-gray-400 shrink-0">#{{ note.id }}</span>
                <span class="text-sm font-medium truncate" :title="note.title">{{ note.title }}</span>
              </div>
              <div class="text-xs text-gray-400 mt-1 truncate">{{ formatTime(note.updated_at) }}</div>
            </button>
            <n-empty v-if="notes.length === 0 && !loading" description="暂无记事本" size="small" class="py-8" />
          </div>
        </aside>

        <section v-if="selectedNote" class="min-w-0 p-3 md:p-4 flex flex-col gap-3">
          <div class="flex items-center gap-3">
            <span class="font-mono text-xs text-gray-400 shrink-0">ID #{{ selectedNote.id }}</span>
            <n-input v-model:value="title" :disabled="mutating" placeholder="记事本标题" maxlength="200" show-count />
          </div>
          <n-input
            v-model:value="content"
            type="textarea"
            :disabled="mutating"
            placeholder="记录 Cookie、Token、备忘等任意内容…"
            class="flex-1 font-mono"
            :autosize="{ minRows: 20 }"
          />
        </section>
        <n-empty v-else description="新建一个记事本开始记录" class="py-20" />
      </div>
    </n-spin>
  </div>
</template>
