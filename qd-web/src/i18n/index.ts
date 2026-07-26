import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import enUS from './en-US'

export function setupI18n() {
  const i18n = createI18n({
    legacy: false,
    locale: localStorage.getItem('locale') || 'zh-CN',
    fallbackLocale: 'en-US',
    messages: {
      'zh-CN': zhCN,
      'en-US': enUS,
    },
  })

  return i18n
}
