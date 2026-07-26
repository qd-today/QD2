<template>
  <div class="notepad">
    <h2>{{ t('notepad.title') }}</h2>
    <el-empty description="Notepad tool coming soon" />
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
</script>
