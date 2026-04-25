<template>
  <div class="chat-container">
    <!-- Sidebar: Session List -->
    <div class="session-sidebar">
      <n-button block type="primary" @click="startNewSession" style="margin-bottom: 12px">
        + New Chat
      </n-button>
      <div class="session-list">
        <div
          v-for="session in sessions"
          :key="session.id"
          class="session-item"
          :class="{ active: session.id === currentSessionId }"
          @click="switchSession(session.id)"
        >
          <div v-if="renamingSessionId === session.id" class="rename-row" @click.stop>
            <input
              class="rename-input"
              v-model="renameValue"
              @keydown.enter="confirmRename(session.id)"
              @keydown.esc="cancelRename"
              ref="renameInputRef"
            />
            <button class="icon-btn ok" @click="confirmRename(session.id)">✓</button>
            <button class="icon-btn cancel" @click="cancelRename">✕</button>
          </div>
          <template v-else>
            <div class="session-info">
              <span class="session-title">{{ session.title || 'New Chat' }}</span>
              <span class="session-date">{{ formatDate(session.created_at) }}</span>
            </div>
            <div class="session-actions" @click.stop>
              <button class="dots-btn" @click.stop="toggleMenu(session.id, $event)">···</button>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- Main Chat Area -->
    <div class="chat-main">
      <!-- Messages -->
      <div class="messages-area" ref="messagesContainer">
        <div v-if="messages.length === 0" class="empty-state">
          <div class="empty-icon">🛡</div>
          <h2>SecuRAG</h2>
          <p>Enterprise Security Knowledge Base Assistant</p>
          <div class="quick-prompts">
            <n-button
              v-for="prompt in quickPrompts"
              :key="prompt"
              quaternary
              size="small"
              @click="sendQuickPrompt(prompt)"
            >
              {{ prompt }}
            </n-button>
          </div>
        </div>

        <div
          v-for="(msg, idx) in messages"
          :key="idx"
          class="message"
          :class="msg.role"
        >
          <div class="message-avatar">
            {{ msg.role === 'user' ? '👤' : '🛡' }}
          </div>
          <div class="message-content">
            <div v-if="msg.role === 'assistant' && msg.statusSteps && msg.statusSteps.length" class="status-steps completed">
              <div v-for="(step, i) in msg.statusSteps" :key="i" class="status-step">
                <span class="step-check">✓</span>
                <span class="step-label">{{ step.label }}</span>
                <span class="step-time">{{ (step.durationMs / 1000).toFixed(1) }}s</span>
              </div>
              <div v-if="msg.model" class="responded-by">Responded by {{ msg.model }}</div>
            </div>
            <div v-if="msg.role === 'assistant'" v-html="renderMarkdown(msg.content)" class="markdown-body" />
            <div v-else>{{ msg.content }}</div>
            <div v-if="msg.role === 'assistant' && msg.content" class="message-actions">
              <button class="action-btn" @click="copyMessage(msg.content, idx)">
                {{ copiedIdx === idx ? '✓ Copied' : '⎘ Copy' }}
              </button>
            </div>
            <div v-if="msg.sources && msg.sources.length > 0" class="sources-section">
              <button class="sources-toggle" @click="toggleSources(idx)">
                📄 {{ msg.sources.length }} {{ msg.sources.length === 1 ? 'source' : 'sources' }}
                <span class="toggle-arrow">{{ expandedSources[idx] ? '▲' : '▼' }}</span>
              </button>
              <div v-if="expandedSources[idx]" class="sources">
                <n-tag
                  v-for="(src, i) in msg.sources"
                  :key="i"
                  size="small"
                  type="info"
                  :bordered="false"
                >
                  📄 {{ src.filename }}
                  <template v-if="src.page_number"> p.{{ src.page_number }}</template>
                </n-tag>
              </div>
            </div>
          </div>
        </div>

        <div v-if="isStreaming" class="message assistant">
          <div class="message-avatar">🛡</div>
          <div class="message-content">
            <div v-if="liveSteps.length > 0" class="status-steps">
              <div v-for="(step, i) in liveSteps" :key="i" class="status-step" :class="{ active: step.durationMs === null }">
                <span v-if="step.durationMs !== null" class="step-check">✓</span>
                <span v-else class="status-dot" />
                <span class="step-label">{{ step.label }}</span>
                <span class="step-time">{{ stepTime(step) }}</span>
              </div>
              <div v-if="selectedModel" class="responded-by">Responded by {{ selectedModel }}</div>
            </div>
            <div v-if="streamingContent" v-html="renderMarkdown(streamingContent)" class="markdown-body" />
            <span v-if="streamingContent" class="cursor-blink">▊</span>
          </div>
        </div>
      </div>

      <!-- Input Area -->
      <div class="input-area">
        <div class="model-picker-row">
          <n-select
            v-model:value="selectedModel"
            :options="modelOptions"
            size="small"
            :consistent-menu-width="false"
            :loading="modelsLoading"
            :disabled="isStreaming"
            class="model-select"
            @update:value="switchModel"
          />
          <n-button
            size="small"
            quaternary
            :disabled="!messages.length || isStreaming"
            @click="exportChat"
            title="Export conversation as Markdown"
          >
            ↓ Export
          </n-button>
        </div>
        <div class="input-wrapper">
          <n-input
            v-model:value="userInput"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 5 }"
            placeholder="Ask a security question..."
            @keydown="handleKeydown"
            :disabled="isStreaming"
          />
          <n-button
            v-if="isStreaming"
            type="error"
            @click="stopStreaming"
            circle
            size="large"
            title="Stop generating"
          >
            <template #icon>
              <n-icon><stop-circle-outline /></n-icon>
            </template>
          </n-button>
          <n-button
            v-else
            type="primary"
            :disabled="!userInput.trim()"
            @click="sendMessage"
            circle
            size="large"
          >
            <template #icon>
              <n-icon><send-outline /></n-icon>
            </template>
          </n-button>
        </div>
      </div>
    </div>
  </div>

  <!-- Dropdown menu rendered at body level to avoid overflow clipping -->
  <Teleport to="body">
    <div
      v-if="openMenuId"
      class="session-menu-portal"
      :style="{ top: menuPos.top + 'px', left: menuPos.left + 'px' }"
      @click.stop
    >
      <button class="menu-item" @click="startRenameById(openMenuId!); openMenuId = null">
        <span class="menu-icon">✎</span> Rename
      </button>
      <div class="menu-divider" />
      <button class="menu-item danger" @click="deleteSession(openMenuId!); openMenuId = null">
        <span class="menu-icon">🗑</span> Delete
      </button>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { NButton, NInput, NIcon, NTag, NSelect } from 'naive-ui'
import { SendOutline, StopCircleOutline } from '@vicons/ionicons5'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

const renamingSessionId = ref<string | null>(null)
const renameValue = ref('')
const renameInputRef = ref<HTMLInputElement | null>(null)
const openMenuId = ref<string | null>(null)
const menuPos = ref({ top: 0, left: 0 })

function toggleMenu(sessionId: string, event: MouseEvent) {
  if (openMenuId.value === sessionId) {
    openMenuId.value = null
    return
  }
  const btn = event.currentTarget as HTMLElement
  const rect = btn.getBoundingClientRect()
  menuPos.value = { top: rect.bottom + 4, left: rect.left }
  openMenuId.value = sessionId
}

function closeMenu() {
  openMenuId.value = null
}

function startRenameById(sessionId: string) {
  const session = sessions.value.find(s => s.id === sessionId)
  if (session) startRename(session)
}

interface Source {
  document_id: string
  filename: string
  chunk_index: number
  page_number: number | null
  content_preview: string
}

interface CompletedStep {
  label: string
  durationMs: number
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  statusSteps?: CompletedStep[]
  model?: string
}

interface Session {
  id: string
  title: string | null
  created_at: string
}

const md = new MarkdownIt({ html: false, linkify: true, breaks: true })
const messagesContainer = ref<HTMLElement>()
const userInput = ref('')
const messages = ref<Message[]>([])
const sessions = ref<Session[]>([])
const currentSessionId = ref<string | null>(null)
const isStreaming = ref(false)
const streamingContent = ref('')
const selectedModel = ref('')
const availableModels = ref<string[]>([])
const modelsLoading = ref(false)
const modelOptions = computed(() =>
  availableModels.value.map(m => ({ label: m, value: m }))
)
let abortController: AbortController | null = null

const copiedIdx = ref<number | null>(null)
const expandedSources = ref<Record<number, boolean>>({})

function stopStreaming() {
  abortController?.abort()
}

interface LiveStep {
  label: string
  startMs: number
  serverTs: number
  durationMs: number | null
}
const liveSteps = ref<LiveStep[]>([])
const liveNow = ref(Date.now())
let liveTimer: ReturnType<typeof setInterval> | null = null

function stepTime(step: LiveStep | CompletedStep): string {
  const ms = step.durationMs !== null ? step.durationMs : liveNow.value - (step as LiveStep).startMs
  return `${(ms / 1000).toFixed(1)}s`
}

function startTimer() {
  liveNow.value = Date.now()
  liveSteps.value = []
  liveTimer = setInterval(() => { liveNow.value = Date.now() }, 100)
}

function stopTimer() {
  if (liveTimer) { clearInterval(liveTimer); liveTimer = null }
}

const quickPrompts = [
  'What is OWASP Top 10?',
  'Explain Zero Trust Architecture',
  'How to prevent SQL injection?',
  'What is incident response?',
]

onMounted(() => {
  loadSessions()
  loadModels()
  document.addEventListener('click', closeMenu)
})

async function loadModels() {
  modelsLoading.value = true
  try {
    const [healthResp, modelsResp] = await Promise.all([
      fetch('/api/health'),
      fetch('/api/settings/models'),
    ])
    if (healthResp.ok) {
      const data = await healthResp.json()
      selectedModel.value = data.llm_model || ''
    }
    if (modelsResp.ok) {
      const data = await modelsResp.json()
      availableModels.value = data.models || []
      if (!selectedModel.value && availableModels.value.length > 0) {
        selectedModel.value = availableModels.value[0]
      }
    }
  } catch {}
  finally {
    modelsLoading.value = false
  }
}

async function switchModel(model: string) {
  try {
    await fetch('/api/settings/model', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    })
    selectedModel.value = model
  } catch (e) {
    console.error('Failed to switch model:', e)
  }
}

onUnmounted(() => {
  document.removeEventListener('click', closeMenu)
})

async function loadSessions() {
  try {
    const resp = await fetch('/api/chat/sessions')
    if (resp.ok) {
      sessions.value = await resp.json()
    }
  } catch (e) {
    console.error('Failed to load sessions:', e)
  }
}

function startNewSession() {
  currentSessionId.value = null
  messages.value = []
  expandedSources.value = {}
}

function startRename(session: Session) {
  renamingSessionId.value = session.id
  renameValue.value = session.title || ''
  nextTick(() => renameInputRef.value?.focus())
}

function cancelRename() {
  renamingSessionId.value = null
  renameValue.value = ''
}

async function confirmRename(sessionId: string) {
  const title = renameValue.value.trim()
  if (!title) return cancelRename()
  try {
    const resp = await fetch(`/api/chat/sessions/${sessionId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    })
    if (resp.ok) {
      const updated = await resp.json()
      const idx = sessions.value.findIndex(s => s.id === sessionId)
      if (idx !== -1) sessions.value[idx].title = updated.title
    }
  } catch (e) {
    console.error('Rename failed:', e)
  } finally {
    cancelRename()
  }
}

async function deleteSession(sessionId: string) {
  try {
    const resp = await fetch(`/api/chat/sessions/${sessionId}`, { method: 'DELETE' })
    if (resp.ok) {
      sessions.value = sessions.value.filter(s => s.id !== sessionId)
      if (currentSessionId.value === sessionId) {
        currentSessionId.value = null
        messages.value = []
      }
    }
  } catch (e) {
    console.error('Delete failed:', e)
  }
}

async function switchSession(sessionId: string) {
  currentSessionId.value = sessionId
  messages.value = []

  try {
    const resp = await fetch(`/api/chat/sessions/${sessionId}/messages`)
    if (resp.ok) {
      const data = await resp.json()
      messages.value = data.map((m: any) => ({
        role: m.role,
        content: m.content,
        sources: m.sources || undefined,
      }))
      await scrollToBottom()
    }
  } catch (e) {
    console.error('Failed to load session messages:', e)
  }
}

function sendQuickPrompt(prompt: string) {
  userInput.value = prompt
  sendMessage()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

async function sendMessage() {
  const text = userInput.value.trim()
  if (!text || isStreaming.value) return

  // Add user message
  messages.value.push({ role: 'user', content: text })
  userInput.value = ''
  isStreaming.value = true
  streamingContent.value = ''
  abortController = new AbortController()
  startTimer()
  await scrollToBottom()

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        session_id: currentSessionId.value,
      }),
      signal: abortController.signal,
    })

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }

    // Capture session ID from header
    const sessionId = resp.headers.get('X-Session-Id')
    if (sessionId) {
      currentSessionId.value = sessionId
    }

    // Read SSE stream
    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let sources: Source[] = []

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const jsonStr = line.slice(6).trim()
        if (!jsonStr) continue

        try {
          const event = JSON.parse(jsonStr)
          if (event.type === 'status') {
            const serverTs: number = event.ts ?? (Date.now() / 1000)
            if (liveSteps.value.length > 0) {
              const last = liveSteps.value[liveSteps.value.length - 1]
              if (last.durationMs === null)
                last.durationMs = Math.round((serverTs - last.serverTs) * 1000)
            }
            liveSteps.value.push({ label: event.label, startMs: Date.now(), serverTs, durationMs: null })
          } else if (event.type === 'token') {
            streamingContent.value += event.content
            await scrollToBottom()
          } else if (event.type === 'guardrail') {
            streamingContent.value = '⚠️ ' + event.content
            await scrollToBottom()
          } else if (event.type === 'done') {
            const serverTs: number = event.ts ?? (Date.now() / 1000)
            if (liveSteps.value.length > 0) {
              const last = liveSteps.value[liveSteps.value.length - 1]
              if (last.durationMs === null)
                last.durationMs = Math.round((serverTs - last.serverTs) * 1000)
            }
            sources = event.sources || []
            if (event.model) {
              // model_name() returns "ollama/llama3.2" — extract just the model part
              const parts = event.model.split('/')
              selectedModel.value = parts.length > 1 ? parts.slice(1).join('/') : event.model
            }
          }
        } catch {
          // skip malformed lines
        }
      }
    }

    // Finalize message
    const completedSteps: CompletedStep[] = liveSteps.value.map(s => ({
      label: s.label,
      durationMs: s.durationMs ?? (Date.now() - s.startMs),
    }))
    messages.value.push({
      role: 'assistant',
      content: streamingContent.value,
      sources,
      statusSteps: completedSteps,
      model: selectedModel.value,
    })

    // Refresh sessions list
    await loadSessions()
  } catch (e: any) {
    if (e?.name === 'AbortError') {
      // User stopped streaming — push whatever was accumulated
      if (streamingContent.value) {
        const completedSteps: CompletedStep[] = liveSteps.value.map(s => ({
          label: s.label,
          durationMs: s.durationMs ?? (Date.now() - s.startMs),
        }))
        messages.value.push({
          role: 'assistant',
          content: streamingContent.value,
          statusSteps: completedSteps,
        })
      }
    } else {
      messages.value.push({
        role: 'assistant',
        content: 'Error: Failed to get response. Please check that the backend is running.',
      })
      console.error('Chat error:', e)
    }
  } finally {
    stopTimer()
    liveSteps.value = []
    isStreaming.value = false
    streamingContent.value = ''
    await scrollToBottom()
  }
}

function copyMessage(content: string, idx: number) {
  navigator.clipboard.writeText(content)
  copiedIdx.value = idx
  setTimeout(() => { if (copiedIdx.value === idx) copiedIdx.value = null }, 2000)
}

function toggleSources(idx: number) {
  expandedSources.value = { ...expandedSources.value, [idx]: !expandedSources.value[idx] }
}

function exportChat() {
  if (!messages.value.length) return
  const lines: string[] = ['# SecuRAG Chat Export\n']
  for (const msg of messages.value) {
    if (msg.role === 'user') {
      lines.push(`**You:** ${msg.content}\n`)
    } else {
      lines.push(`**SecuRAG:** ${msg.content}\n`)
      if (msg.sources?.length) {
        lines.push(`*Sources: ${msg.sources.map(s => s.filename).join(', ')}*\n`)
      }
    }
  }
  const session = sessions.value.find(s => s.id === currentSessionId.value)
  const titleSlug = (session?.title || 'chat')
    .trim()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .slice(0, 60)
  const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${titleSlug}.md`
  a.click()
  URL.revokeObjectURL(url)
}

function renderMarkdown(text: string): string {
  return DOMPurify.sanitize(md.render(text))
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

async function scrollToBottom() {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}
</script>

<style scoped>
.chat-container {
  display: flex;
  height: 100%;
  color: #e0e0e0;
}

.session-sidebar {
  width: 240px;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  padding: 16px;
  overflow-y: auto;
  background: rgba(0, 0, 0, 0.2);
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.session-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.session-item:hover .session-actions {
  opacity: 1;
}

.session-item.active {
  background: rgba(99, 226, 183, 0.1);
  border: 1px solid rgba(99, 226, 183, 0.2);
}

.session-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.session-title {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-date {
  font-size: 11px;
  color: #888;
}

.session-actions {
  position: relative;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}

.dots-btn {
  background: none;
  border: none;
  color: #aaa;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 16px;
  line-height: 1;
  letter-spacing: 1px;
}

.dots-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #fff;
}

.session-menu-portal {
  position: fixed;
  background: #2a2a2a;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  padding: 4px;
  min-width: 150px;
  z-index: 9999;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  background: none;
  border: none;
  color: #e0e0e0;
  cursor: pointer;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
  text-align: left;
}

.menu-item:hover {
  background: rgba(255, 255, 255, 0.08);
}

.menu-item.danger {
  color: #ff6b6b;
}

.menu-item.danger:hover {
  background: rgba(255, 80, 80, 0.15);
}

.menu-icon {
  font-size: 14px;
  width: 16px;
  text-align: center;
}

.menu-divider {
  height: 1px;
  background: rgba(255, 255, 255, 0.08);
  margin: 4px 0;
}

.icon-btn {
  background: none;
  border: none;
  color: #aaa;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1;
}

.icon-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.icon-btn.ok:hover {
  background: rgba(99, 226, 183, 0.2);
  color: #63e2b7;
}

.rename-row {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
}

.rename-input {
  flex: 1;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(99, 226, 183, 0.4);
  border-radius: 4px;
  color: #fff;
  font-size: 13px;
  padding: 2px 6px;
  outline: none;
  min-width: 0;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: #888;
}

.empty-icon {
  font-size: 48px;
}

.empty-state h2 {
  color: #63e2b7;
  font-size: 28px;
  margin: 0;
}

.empty-state p {
  font-size: 14px;
}

.quick-prompts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
  justify-content: center;
  max-width: 500px;
}

.message {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  max-width: 800px;
  margin-left: auto;
  margin-right: auto;
}

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.06);
}

.message.user .message-avatar {
  background: rgba(99, 226, 183, 0.15);
}

.message-content {
  flex: 1;
  min-width: 0;
  line-height: 1.7;
  font-size: 14px;
}

.message.user .message-content {
  color: #f0f0f0;
}

.markdown-body :deep(pre) {
  background: rgba(0, 0, 0, 0.3);
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
  margin: 8px 0;
}

.markdown-body :deep(code) {
  background: rgba(0, 0, 0, 0.2);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}

.markdown-body :deep(ul), .markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 8px 0;
}

.markdown-body :deep(p) {
  margin: 4px 0;
}

.message-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  opacity: 0;
  transition: opacity 0.15s;
}

.message:hover .message-actions {
  opacity: 1;
}

.action-btn {
  background: rgba(255, 255, 255, 0.06);
  border: none;
  color: #888;
  cursor: pointer;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  color: #ccc;
}

.sources-section {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.sources-toggle {
  background: none;
  border: none;
  color: #666;
  cursor: pointer;
  font-size: 12px;
  padding: 2px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.sources-toggle:hover {
  color: #aaa;
}

.toggle-arrow {
  font-size: 10px;
}

.sources {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.status-steps {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.status-steps.completed {
  opacity: 0.6;
}

.status-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #888;
  font-variant-numeric: tabular-nums;
}

.status-step.active {
  color: #aaa;
}

.step-check {
  width: 14px;
  text-align: center;
  color: #63e2b7;
  font-size: 11px;
  flex-shrink: 0;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #63e2b7;
  animation: pulse 1.2s ease-in-out infinite;
  flex-shrink: 0;
  margin: 0 3px;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.8); }
}

.step-label {
  flex: 1;
}

.step-time {
  color: #555;
  min-width: 36px;
  text-align: right;
}

.responded-by {
  font-size: 11px;
  color: #4a4a4a;
  margin-top: 4px;
  padding-left: 2px;
}

.cursor-blink {
  animation: blink 1s infinite;
  color: #63e2b7;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.input-area {
  padding: 16px 24px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.model-picker-row {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.model-select {
  width: 200px;
}

.input-wrapper {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  max-width: 800px;
  margin: 0 auto;
}
</style>
