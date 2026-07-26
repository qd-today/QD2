import axios from 'axios'
import Cookies from 'js-cookie'
import router from '@/router'

const api = axios.create({
  baseURL: '',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor: attach access token
api.interceptors.request.use(
  (config) => {
    const token = Cookies.get('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor: handle 401 and refresh token
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // If 401 and not already retrying
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      const refreshToken = Cookies.get('refresh_token')
      if (refreshToken) {
        try {
          const response = await axios.post('/api/auth/refresh', {
            refresh_token: refreshToken,
          })

          const { access_token, refresh_token: newRefresh } = response.data
          Cookies.set('access_token', access_token, { expires: 1 })
          Cookies.set('refresh_token', newRefresh, { expires: 7 })

          originalRequest.headers.Authorization = `Bearer ${access_token}`
          return api(originalRequest)
        } catch {
          // Refresh failed, redirect to login
          Cookies.remove('access_token')
          Cookies.remove('refresh_token')
          router.push('/login')
        }
      } else {
        // No refresh token, redirect to login
        router.push('/login')
      }
    }

    return Promise.reject(error)
  }
)

export default api
