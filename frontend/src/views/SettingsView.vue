<template>
  <div class="settings-container">
    <div class="settings-header">
      <h1>Settings</h1>
      <p class="subtitle">System configuration and status</p>
    </div>

    <n-card title="System Status" size="small" style="margin-bottom: 16px">
      <n-descriptions :column="1" label-placement="left" bordered size="small">
        <n-descriptions-item label="Backend">
          <n-tag :type="healthOk ? 'success' : 'error'" size="small">
            {{ healthOk ? 'Connected' : 'Disconnected' }}
          </n-tag>
        </n-descriptions-item>
        <n-descriptions-item label="LLM Provider">
          <n-tag size="small">{{ health.llm_provider || '—' }}</n-tag>
        </n-descriptions-item>
        <n-descriptions-item label="Guardrails">
          <n-tag :type="health.guardrails_enabled ? 'success' : 'warning'" size="small">
            {{ health.guardrails_enabled ? 'Enabled' : 'Disabled' }}
          </n-tag>
        </n-descriptions-item>
      </n-descriptions>
    </n-card>

    <n-card title="About" size="small">
      <p>SecuRAG v0.1.0</p>
      <p style="color: #888; font-size: 13px; margin-top: 8px;">
        Enterprise security knowledge base chatbot with RAG and AI safety guardrails.
      </p>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NCard, NDescriptions, NDescriptionsItem, NTag } from 'naive-ui'

const healthOk = ref(false)
const health = ref<Record<string, any>>({})

onMounted(async () => {
  try {
    const resp = await fetch('/api/health')
    if (resp.ok) {
      health.value = await resp.json()
      healthOk.value = true
    }
  } catch {
    healthOk.value = false
  }
})
</script>

<style scoped>
.settings-container {
  max-width: 600px;
  margin: 0 auto;
  padding: 32px 24px;
  color: #e0e0e0;
}

.settings-header {
  margin-bottom: 24px;
}

.settings-header h1 {
  font-size: 24px;
  color: #63e2b7;
  margin: 0 0 4px;
}

.subtitle {
  color: #888;
  font-size: 14px;
}
</style>
