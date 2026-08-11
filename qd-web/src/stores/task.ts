import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'

interface Task {
  id: number
  template_id: number
  name: string
  description?: string
  schedule_config: Record<string, unknown>
  status: string
  variables: Record<string, unknown>
  execution_config: Record<string, unknown>
  group_id?: number | null
  next_run_at?: string | null
  run_count: number
  last_run_at?: string
  last_status?: string
  success_count: number
  failed_count: number
  last_success_at?: string | null
  created_at: string
  updated_at: string
}

export const useTaskStore = defineStore('task', () => {
  const tasks = ref<Task[]>([])
  const total = ref(0)
  const loading = ref(false)

  async function fetchTasks(page = 1, pageSize = 20, status = '') {
    loading.value = true
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: pageSize.toString(),
      })
      if (status) params.append('status', status)

      const response = await api.get(`/api/tasks?${params}`)
      tasks.value = response.data.items
      total.value = response.data.total
    } finally {
      loading.value = false
    }
  }

  async function createTask(data: Partial<Task>) {
    const response = await api.post('/api/tasks', data)
    tasks.value.unshift(response.data)
    total.value++
    return response.data
  }

  async function updateTask(id: number, data: Partial<Task>) {
    const response = await api.put(`/api/tasks/${id}`, data)
    const index = tasks.value.findIndex((t) => t.id === id)
    if (index !== -1) {
      tasks.value[index] = response.data
    }
    return response.data
  }

  async function deleteTask(id: number) {
    await api.delete(`/api/tasks/${id}`)
    tasks.value = tasks.value.filter((t) => t.id !== id)
    total.value--
  }

  async function runTask(id: number) {
    const response = await api.post(`/api/tasks/${id}/run`)
    return response.data
  }

  return {
    tasks,
    total,
    loading,
    fetchTasks,
    createTask,
    updateTask,
    deleteTask,
    runTask,
  }
})
