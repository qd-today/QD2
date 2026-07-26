import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(localStorage.getItem('qd2-theme') === 'dark')

  function toggle() {
    isDark.value = !isDark.value
    localStorage.setItem('qd2-theme', isDark.value ? 'dark' : 'light')
  }

  return { isDark, toggle }
})
