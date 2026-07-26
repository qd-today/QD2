<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import api from '@/api'

const message = useMessage()
const dialog = useDialog()

interface PluginInfo {
  name: string
  enabled: boolean
  is_default: boolean
}

const plugins = ref<PluginInfo[]>([])
const loading = ref(false)

async function fetchPlugins() {
  loading.value = true
  try {
    const response = await api.get('/api/plugins')
    plugins.value = response.data.plugins
  } finally {
    loading.value = false
  }
}

function uninstallPlugin(name: string) {
  dialog.warning({
    title: '卸载插件',
    content: `确定卸载插件「${name}」？`,
    positiveText: '卸载',
    negativeText: '取消',
    onPositiveClick: async () => {
      await api.delete(`/api/plugins/${name}`)
      message.success('已卸载')
      await fetchPlugins()
    },
  })
}

onMounted(fetchPlugins)
</script>

<template>
  <div>
    <h2 class="text-lg font-semibold mb-4">插件</h2>
    <n-spin :show="loading">
      <n-empty v-if="plugins.length === 0 && !loading" description="暂无插件" class="mt-16" />
      <n-table v-else :bordered="false" size="small">
        <thead>
          <tr>
            <th>名称</th>
            <th>状态</th>
            <th>类型</th>
            <th class="!text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in plugins" :key="row.name">
            <td class="font-medium">{{ row.name }}</td>
            <td>
              <n-tag :type="row.enabled ? 'success' : 'default'" size="small" round>
                {{ row.enabled ? '启用' : '禁用' }}
              </n-tag>
            </td>
            <td class="text-gray-400">{{ row.is_default ? '内置' : '第三方' }}</td>
            <td class="!text-right">
              <n-button
                v-if="!row.is_default"
                size="tiny"
                quaternary
                type="error"
                @click="uninstallPlugin(row.name)"
              >
                卸载
              </n-button>
            </td>
          </tr>
        </tbody>
      </n-table>
    </n-spin>
  </div>
</template>
