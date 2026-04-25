<template>
  <div class="settings-container">
    <div class="settings-header">
      <h1>Settings</h1>
      <p class="subtitle">System configuration, service health, and knowledge base statistics</p>
    </div>

    <!-- Service Health -->
    <n-card title="Service Health" size="small" style="margin-bottom: 16px">
      <template #header-extra>
        <n-button size="tiny" quaternary @click="refreshHealth" :loading="healthLoading">
          Refresh
        </n-button>
      </template>
      <div class="service-grid">
        <div
          v-for="(ok, name) in health.services || {}"
          :key="name"
          class="service-card"
          :class="ok ? 'up' : 'down'"
        >
          <div class="service-indicator" :class="ok ? 'up' : 'down'" />
          <div class="service-info">
            <span class="service-name">{{ serviceLabels[name] || name }}</span>
            <span class="service-status">{{ ok ? 'Connected' : 'Disconnected' }}</span>
          </div>
        </div>
      </div>
      <n-alert
        v-if="!healthOk && !healthLoading"
        type="error"
        title="Backend Unreachable"
        style="margin-top: 12px"
      >
        Cannot connect to the backend API. Make sure all services are running with <code>make up</code>.
      </n-alert>
    </n-card>

    <!-- LLM Configuration -->
    <n-card title="LLM Configuration" size="small" style="margin-bottom: 16px">
      <n-descriptions :column="2" label-placement="left" bordered size="small">
        <n-descriptions-item label="Provider">
          <n-tag size="small" :type="health.llm_provider === 'ollama' ? 'success' : 'info'">
            {{ (health.llm_provider || '—').toUpperCase() }}
          </n-tag>
        </n-descriptions-item>
        <n-descriptions-item label="Model">
          <code>{{ health.llm_model || '—' }}</code>
        </n-descriptions-item>
        <n-descriptions-item label="Embedding Model">
          <code>{{ health.embedding_model || '—' }}</code>
        </n-descriptions-item>
        <n-descriptions-item label="Guardrails">
          <n-tag :type="health.guardrails_enabled ? 'success' : 'warning'" size="small">
            {{ health.guardrails_enabled ? 'Enabled' : 'Disabled' }}
          </n-tag>
        </n-descriptions-item>
      </n-descriptions>

      <div class="provider-switch">
        <span class="switch-label">Switch provider</span>
        <n-button-group>
          <n-button
            size="small"
            :type="health.llm_provider === 'ollama' ? 'primary' : 'default'"
            :loading="switchingProvider"
            :disabled="health.llm_provider === 'ollama'"
            @click="switchProvider('ollama')"
          >
            Ollama (Local)
          </n-button>
          <n-button
            size="small"
            :type="health.llm_provider === 'vertexai' ? 'primary' : 'default'"
            :loading="switchingProvider"
            :disabled="health.llm_provider === 'vertexai'"
            @click="switchProvider('vertexai')"
          >
            Vertex AI
          </n-button>
        </n-button-group>
        <n-tag v-if="switchError" type="error" size="small">{{ switchError }}</n-tag>
      </div>
    </n-card>

    <!-- RAG Configuration -->
    <n-card title="RAG Pipeline" size="small" style="margin-bottom: 16px">
      <n-descriptions :column="3" label-placement="left" bordered size="small">
        <n-descriptions-item label="Chunk Size">
          {{ health.chunk_size || '—' }} chars
        </n-descriptions-item>
        <n-descriptions-item label="Chunk Overlap">
          {{ health.chunk_overlap || '—' }} chars
        </n-descriptions-item>
        <n-descriptions-item label="Top-K Results">
          {{ health.retrieval_top_k || '—' }}
        </n-descriptions-item>
      </n-descriptions>
    </n-card>

    <!-- Knowledge Base Stats -->
    <n-card title="Knowledge Base" size="small" style="margin-bottom: 16px">
      <div class="stats-grid">
        <div class="stat-card">
          <span class="stat-value">{{ stats.total_documents }}</span>
          <span class="stat-label">Documents</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ stats.total_chunks }}</span>
          <span class="stat-label">Chunks</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ stats.total_sessions }}</span>
          <span class="stat-label">Chat Sessions</span>
        </div>
        <div class="stat-card">
          <span class="stat-value">{{ formatSize(stats.total_size) }}</span>
          <span class="stat-label">Total Size</span>
        </div>
      </div>
      <div v-if="docList.length > 0" class="doc-list">
        <div v-for="doc in docList" :key="doc.id" class="doc-item">
          <span class="doc-name">{{ doc.filename }}</span>
          <span class="doc-meta">{{ doc.chunk_count }} chunks · {{ formatSize(doc.file_size) }}</span>
        </div>
      </div>
    </n-card>

    <!-- About -->
    <n-card title="About" size="small">
      <n-descriptions :column="1" label-placement="left" size="small">
        <n-descriptions-item label="Version">v0.1.0</n-descriptions-item>
        <n-descriptions-item label="Stack">FastAPI + Vue 3 + ChromaDB + Ollama</n-descriptions-item>
        <n-descriptions-item label="License">MIT</n-descriptions-item>
      </n-descriptions>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  NCard,
  NDescriptions,
  NDescriptionsItem,
  NTag,
  NButton,
  NButtonGroup,
  NAlert,
} from 'naive-ui'

const healthOk = ref(false)
const healthLoading = ref(false)
const health = ref<Record<string, any>>({})
const stats = ref({ total_documents: 0, total_chunks: 0, total_sessions: 0, total_size: 0 })
const docList = ref<Array<{ id: string; filename: string; chunk_count: number; file_size: number }>>([])

const switchingProvider = ref(false)
const switchError = ref('')

const serviceLabels: Record<string, string> = {
  postgres: 'PostgreSQL',
  chromadb: 'ChromaDB',
  ollama: 'Ollama LLM',
}

onMounted(() => {
  refreshHealth()
  loadStats()
})

async function refreshHealth() {
  healthLoading.value = true
  try {
    const resp = await fetch('/api/health')
    if (resp.ok) {
      health.value = await resp.json()
      healthOk.value = true
    } else {
      healthOk.value = false
    }
  } catch {
    healthOk.value = false
  } finally {
    healthLoading.value = false
  }
}

async function switchProvider(provider: string) {
  switchingProvider.value = true
  switchError.value = ''
  try {
    const resp = await fetch('/api/settings/provider', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider }),
    })
    if (resp.ok) {
      await refreshHealth()
    } else {
      const err = await resp.json()
      switchError.value = err.detail || 'Switch failed'
    }
  } catch {
    switchError.value = 'Network error'
  } finally {
    switchingProvider.value = false
  }
}

async function loadStats() {
  try {
    const [docsResp, sessionsResp] = await Promise.all([
      fetch('/api/documents'),
      fetch('/api/chat/sessions'),
    ])
    if (docsResp.ok) {
      const data = await docsResp.json()
      const docs = data.documents || []
      docList.value = docs
      stats.value.total_documents = docs.length
      stats.value.total_chunks = docs.reduce((sum: number, d: any) => sum + (d.chunk_count || 0), 0)
      stats.value.total_size = docs.reduce((sum: number, d: any) => sum + (d.file_size || 0), 0)
    }
    if (sessionsResp.ok) {
      const sessions = await sessionsResp.json()
      stats.value.total_sessions = sessions.length
    }
  } catch {
    // stats are non-critical
  }
}

function formatSize(bytes: number): string {
  if (!bytes) return '0 B'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.settings-container {
  max-width: 700px;
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

.service-grid {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.service-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  flex: 1;
  min-width: 160px;
}

.service-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.service-indicator.up {
  background: #63e2b7;
  box-shadow: 0 0 6px rgba(99, 226, 183, 0.5);
}

.service-indicator.down {
  background: #e88080;
  box-shadow: 0 0 6px rgba(232, 128, 128, 0.5);
}

.service-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.service-name {
  font-size: 13px;
  font-weight: 600;
}

.service-status {
  font-size: 11px;
  color: #888;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 16px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #63e2b7;
}

.stat-label {
  font-size: 12px;
  color: #888;
}

code {
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}

.provider-switch {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.switch-label {
  font-size: 13px;
  color: #888;
  white-space: nowrap;
}

.doc-list {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.doc-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  padding: 2px 0;
}

.doc-name {
  color: #ccc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 65%;
}

.doc-meta {
  color: #666;
  white-space: nowrap;
}
</style>
