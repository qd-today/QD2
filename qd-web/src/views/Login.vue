<template>
  <div class="login-container">
    <el-card class="login-card">
      <template #header>
        <h2>{{ isRegister ? t('auth.registerTitle') : t('auth.loginTitle') }}</h2>
      </template>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="auto"
        @submit.prevent="handleSubmit"
      >
        <el-form-item :label="t('auth.username')" prop="username">
          <el-input v-model="form.username" :placeholder="t('auth.username')" />
        </el-form-item>

        <el-form-item :label="t('auth.password')" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            :placeholder="t('auth.password')"
            show-password
          />
        </el-form-item>

        <el-form-item v-if="isRegister" label="确认密码" prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            show-password
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%">
            {{ isRegister ? t('common.register') : t('common.login') }}
          </el-button>
        </el-form-item>

        <el-form-item>
          <el-button link type="primary" @click="isRegister = !isRegister" style="width: 100%">
            {{ isRegister ? '已有账号？去登录' : '没有账号？去注册' }}
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import api from '@/api'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const formRef = ref()
const loading = ref(false)
const isRegister = ref(false)

const form = reactive({
  username: '',
  password: '',
  confirmPassword: '',
})

const validateConfirmPassword = (_rule: any, value: string, callback: any) => {
  if (value !== form.password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' },
  ],
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    if (isRegister.value) {
      // Register
      await api.post('/api/auth/register', {
        username: form.username,
        password: form.password,
      })
      ElMessage.success('注册成功，请登录')
      isRegister.value = false
    } else {
      // Login
      await authStore.login(form.username, form.password)
      ElMessage.success(t('auth.loginSuccess'))
      const redirect = (route.query.redirect as string) || '/'
      router.push(redirect)
    }
  } catch (err: any) {
    const msg = err.response?.data?.detail || (isRegister.value ? '注册失败' : t('auth.loginFailed'))
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background-color: #f5f5f5;
}

.login-card {
  width: 400px;
}
</style>
