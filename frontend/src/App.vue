<template>
  <n-config-provider :theme="darkTheme">
    <n-message-provider>
    <n-layout has-sider style="height: 100vh">
      <n-layout-sider
        bordered
        :width="220"
        :collapsed-width="64"
        collapse-mode="width"
        :collapsed="collapsed"
        show-trigger
        @collapse="collapsed = true"
        @expand="collapsed = false"
        style="background: #1a1a2e"
      >
        <div class="logo" v-show="!collapsed">
          <span class="logo-icon">🛡</span>
          <span class="logo-text">SecuRAG</span>
        </div>
        <div class="logo" v-show="collapsed">
          <span class="logo-icon">🛡</span>
        </div>
        <n-menu
          :collapsed="collapsed"
          :collapsed-width="64"
          :collapsed-icon-size="22"
          :options="menuOptions"
          :value="currentRoute"
          @update:value="handleMenuSelect"
        />
      </n-layout-sider>
      <n-layout-content style="background: #0f0f1a">
        <router-view />
      </n-layout-content>
    </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  NConfigProvider,
  NLayout,
  NLayoutSider,
  NLayoutContent,
  NMenu,
  NMessageProvider,
  NIcon,
  darkTheme,
} from 'naive-ui'
import type { MenuOption } from 'naive-ui'
import {
  ChatbubbleEllipsesOutline,
  DocumentTextOutline,
  SettingsOutline,
} from '@vicons/ionicons5'

const router = useRouter()
const route = useRoute()
const collapsed = ref(false)

const currentRoute = computed(() => route.path)

function renderIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const menuOptions: MenuOption[] = [
  {
    label: 'Chat',
    key: '/',
    icon: renderIcon(ChatbubbleEllipsesOutline),
  },
  {
    label: 'Documents',
    key: '/documents',
    icon: renderIcon(DocumentTextOutline),
  },
  {
    label: 'Settings',
    key: '/settings',
    icon: renderIcon(SettingsOutline),
  },
]

function handleMenuSelect(key: string) {
  router.push(key)
}
</script>

<style scoped>
.logo {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.logo-icon {
  font-size: 24px;
}

.logo-text {
  font-size: 20px;
  font-weight: 700;
  color: #63e2b7;
  letter-spacing: 1px;
}
</style>
