<template>
  <div class="plugins">
    <h2>{{ t('plugin.title') }}</h2>

    <el-table :data="plugins" v-loading="loading" stripe>
      <el-table-column prop="name" label="Name" />
      <el-table-column label="Status" width="120">
        <template #default="{ row }">
          <el-tag :type="row.enabled ? 'success' : 'info'">
            {{ row.enabled ? t('plugin.enabled') : t('plugin.disabled') }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Type" width="120">
        <template #default="{ row }">
          {{ row.is_default ? t('plugin.default') : t('plugin.thirdParty') }}
        </template>
      </el-table-column>
      <el-table-column label="Actions" width="150">
        <template #default="{ row }">
          <el-button
            v-if="!row.is_default"
            size="small"
            type="danger"
            @click="uninstallPlugin(row.name)"
          >
            {{ t('plugin.uninstall') }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'

const { t } = useI18n()

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

async function uninstallPlugin(name: string) {
  await ElMessageBox.confirm(`Uninstall plugin "${name}"?`)
  await api.delete(`/api/plugins/${name}`)
  ElMessage.success(t('common.success'))
  await fetchPlugins()
}

onMounted(() => {
  fetchPlugins()
})
</script>
