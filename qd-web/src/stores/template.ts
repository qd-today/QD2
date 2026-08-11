import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/api'

interface Template {
  id: number
  name: string
  description?: string
  template_data: Record<string, unknown>
  variables: Record<string, unknown>
  tags: string[]
  is_public: boolean
  enabled: boolean
  run_count: number
  last_success_at?: string | null
  created_at: string
  updated_at: string
}

export const useTemplateStore = defineStore('template', () => {
  const templates = ref<Template[]>([])
  const total = ref(0)
  const loading = ref(false)

  async function fetchTemplates(page = 1, pageSize = 20, search = '') {
    loading.value = true
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        page_size: pageSize.toString(),
      })
      if (search) params.append('search', search)

      const response = await api.get(`/api/templates?${params}`)
      templates.value = response.data.items
      total.value = response.data.total
    } finally {
      loading.value = false
    }
  }

  async function createTemplate(data: Partial<Template>) {
    const response = await api.post('/api/templates', data)
    templates.value.unshift(response.data)
    total.value++
    return response.data
  }

  async function updateTemplate(id: number, data: Partial<Template>) {
    const response = await api.put(`/api/templates/${id}`, data)
    const index = templates.value.findIndex((t) => t.id === id)
    if (index !== -1) {
      templates.value[index] = response.data
    }
    return response.data
  }

  async function deleteTemplate(id: number) {
    await api.delete(`/api/templates/${id}`)
    templates.value = templates.value.filter((t) => t.id !== id)
    total.value--
  }

  async function importTemplate(data: any) {
    const response = await api.post('/api/templates/import', data)
    templates.value.unshift(response.data)
    total.value++
    return response.data
  }

  return {
    templates,
    total,
    loading,
    fetchTemplates,
    createTemplate,
    updateTemplate,
    deleteTemplate,
    importTemplate,
  }
})
