import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import Cookies from 'js-cookie'
import api from '@/api'

interface User {
  id: number
  username: string
  email?: string
  role: string
  display_name?: string
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const accessToken = ref<string | null>(Cookies.get('access_token') || null)
  const refreshToken = ref<string | null>(Cookies.get('refresh_token') || null)

  const isAuthenticated = computed(() => !!accessToken.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function login(username: string, password: string) {
    const response = await api.post('/api/auth/login', { username, password })
    const { access_token, refresh_token } = response.data

    accessToken.value = access_token
    refreshToken.value = refresh_token

    Cookies.set('access_token', access_token, { expires: 1 })
    Cookies.set('refresh_token', refresh_token, { expires: 7 })

    await fetchUser()
  }

  async function fetchUser() {
    try {
      const response = await api.get('/api/auth/me')
      user.value = response.data
    } catch {
      logout()
    }
  }

  async function refreshAccessToken() {
    try {
      const response = await api.post('/api/auth/refresh', {
        refresh_token: refreshToken.value,
      })
      const { access_token, refresh_token: new_refresh } = response.data

      accessToken.value = access_token
      refreshToken.value = new_refresh

      Cookies.set('access_token', access_token, { expires: 1 })
      Cookies.set('refresh_token', new_refresh, { expires: 7 })

      return access_token
    } catch {
      logout()
      return null
    }
  }

  function logout() {
    user.value = null
    accessToken.value = null
    refreshToken.value = null

    Cookies.remove('access_token')
    Cookies.remove('refresh_token')
  }

  // Initialize: fetch user if token exists
  if (accessToken.value) {
    fetchUser()
  }

  return {
    user,
    accessToken,
    refreshToken,
    isAuthenticated,
    isAdmin,
    login,
    fetchUser,
    refreshAccessToken,
    logout,
  }
})
