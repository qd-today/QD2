<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { NIcon, type MenuOption } from 'naive-ui'
import {
  SpeedometerOutline,
  DocumentTextOutline,
  TimerOutline,
  CloudDownloadOutline,
  NotificationsOutline,
  ExtensionPuzzleOutline,
  BookOutline,
  PeopleOutline,
  MoonOutline,
  SunnyOutline,
  LogOutOutline,
  TerminalOutline,
} from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import LogDrawer from '@/components/LogDrawer.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const themeStore = useThemeStore()

const collapsed = ref(false)
const showLogs = ref(false)

function renderIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const menuOptions = computed<MenuOption[]>(() => {
  const items: MenuOption[] = [
    {
      label: () => h(RouterLink, { to: '/' }, { default: () => '仪表盘' }),
      key: '/',
      icon: renderIcon(SpeedometerOutline),
    },
    {
      label: () => h(RouterLink, { to: '/tasks' }, { default: () => '任务管理' }),
      key: '/tasks',
      icon: renderIcon(TimerOutline),
    },
    {
      label: () => h(RouterLink, { to: '/templates' }, { default: () => '模板管理' }),
      key: '/templates',
      icon: renderIcon(DocumentTextOutline),
    },
    {
      label: () => h(RouterLink, { to: '/template-store' }, { default: () => '模板库' }),
      key: '/template-store',
      icon: renderIcon(CloudDownloadOutline),
    },
    {
      label: () => h(RouterLink, { to: '/notifications' }, { default: () => '通知渠道' }),
      key: '/notifications',
      icon: renderIcon(NotificationsOutline),
    },
    {
      label: () => h(RouterLink, { to: '/plugins' }, { default: () => '插件' }),
      key: '/plugins',
      icon: renderIcon(ExtensionPuzzleOutline),
    },
    {
      label: () => h(RouterLink, { to: '/notepad' }, { default: () => '记事本' }),
      key: '/notepad',
      icon: renderIcon(BookOutline),
    },
  ]
  if (authStore.isAdmin) {
    items.push({
      label: () => h(RouterLink, { to: '/admin' }, { default: () => '用户管理' }),
      key: '/admin',
      icon: renderIcon(PeopleOutline),
    })
  }
  return items
})

const activeKey = computed(() => {
  const p = route.path
  if (p.startsWith('/templates/')) return '/templates'
  return p
})

function logout() {
  authStore.logout()
  router.push('/login')
}

function handleMenuSelect(key: string) {
  if (key !== route.path) router.push(key)
}

function openLogs() {
  showLogs.value = true
}

onMounted(() => window.addEventListener('qd:open-logs', openLogs))
onBeforeUnmount(() => window.removeEventListener('qd:open-logs', openLogs))
</script>

<template>
  <n-layout has-sider class="h-full">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="220"
      :collapsed="collapsed"
      show-trigger
      @collapse="collapsed = true"
      @expand="collapsed = false"
    >
      <div class="flex items-center justify-center h-14 gap-2">
        <span class="text-xl font-bold text-indigo-500">QD2</span>
        <span v-if="!collapsed" class="text-xs text-gray-400 mt-1">定时任务</span>
      </div>
      <n-menu
        :value="activeKey"
        :collapsed="collapsed"
        :collapsed-width="64"
        :collapsed-icon-size="20"
        :options="menuOptions"
        @update:value="handleMenuSelect"
      />
    </n-layout-sider>

    <n-layout class="h-full">
      <n-layout-header bordered class="h-14 flex items-center justify-between px-4">
        <div class="text-sm text-gray-400">
          {{ route.meta.title || '' }}
        </div>
        <div class="flex items-center gap-2">
          <n-button quaternary circle title="实时日志" @click="showLogs = true">
            <template #icon>
              <n-icon><TerminalOutline /></n-icon>
            </template>
          </n-button>
          <n-button quaternary circle @click="themeStore.toggle()">
            <template #icon>
              <n-icon>
                <MoonOutline v-if="!themeStore.isDark" />
                <SunnyOutline v-else />
              </n-icon>
            </template>
          </n-button>
          <n-dropdown
            :options="[{ label: '退出登录', key: 'logout', icon: renderIcon(LogOutOutline) }]"
            @select="logout"
          >
            <n-button quaternary class="flex items-center gap-1">
              <n-avatar round size="small" class="bg-indigo-500">
                {{ (authStore.user?.username || '?')[0].toUpperCase() }}
              </n-avatar>
              <span class="ml-1">{{ authStore.user?.display_name || authStore.user?.username }}</span>
            </n-button>
          </n-dropdown>
        </div>
      </n-layout-header>
      <n-layout-content
        content-class="p-4 md:p-6"
        class="h-[calc(100%-3.5rem)]"
        :native-scrollbar="false"
      >
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>

  <LogDrawer v-model:show="showLogs" />
</template>
