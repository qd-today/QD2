<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import api from '@/api'

const router = useRouter()
const route = useRoute()
const message = useMessage()
const authStore = useAuthStore()

const mode = ref<'login' | 'register'>('login')
const loading = ref(false)
const form = ref({ username: '', password: '', email: '' })

async function submit() {
  if (!form.value.username || !form.value.password) {
    message.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    if (mode.value === 'register') {
      await api.post('/api/auth/register', {
        username: form.value.username,
        password: form.value.password,
        email: form.value.email || undefined,
      })
      message.success('注册成功，正在登录…')
    }
    await authStore.login(form.value.username, form.value.password)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch (e: any) {
    message.error(e.response?.data?.detail || (mode.value === 'register' ? '注册失败' : '登录失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div
    class="h-full flex items-center justify-center bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-400"
  >
    <div class="w-full max-w-sm mx-4">
      <n-card :bordered="false" class="shadow-2xl rounded-2xl">
        <div class="text-center mb-6">
          <h1 class="text-3xl font-bold text-indigo-600">QD2</h1>
          <p class="text-gray-400 text-sm mt-1">HTTP 定时任务自动化框架</p>
        </div>
        <n-form @keyup.enter="submit">
          <n-form-item label="用户名" :show-feedback="false" class="mb-3">
            <n-input v-model:value="form.username" placeholder="用户名" />
          </n-form-item>
          <n-form-item label="密码" :show-feedback="false" class="mb-3">
            <n-input
              v-model:value="form.password"
              type="password"
              show-password-on="click"
              placeholder="密码"
            />
          </n-form-item>
          <n-form-item
            v-if="mode === 'register'"
            label="邮箱 (可选)"
            :show-feedback="false"
            class="mb-3"
          >
            <n-input v-model:value="form.email" placeholder="email@example.com" />
          </n-form-item>
        </n-form>
        <n-button type="primary" block size="large" :loading="loading" class="mt-4" @click="submit">
          {{ mode === 'login' ? '登 录' : '注 册' }}
        </n-button>
        <div class="text-center mt-4">
          <n-button text type="primary" @click="mode = mode === 'login' ? 'register' : 'login'">
            {{ mode === 'login' ? '没有账号？注册' : '已有账号？登录' }}
          </n-button>
        </div>
      </n-card>
    </div>
  </div>
</template>
