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
          <span class="session-title">{{ session.title || 'New Chat' }}</span>
          <span class="session-date">{{ formatDate(session.created_at) }}</span>
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
            <div v-if="msg.role === 'assistant'" v-html="renderMarkdown(msg.content)" class="markdown-body" />
            <div v-else>{{ msg.content }}</div>
            <div v-if="msg.sources && msg.sources.length > 0" class="sources">
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

        <div v-if="isStreaming" class="message assistant">
          <div class="message-avatar">🛡</div>
          <div class="message-content">
            <div v-html="renderMarkdown(streamingContent)" class="markdown-body" />
            <span class="cursor-blink">▊</span>
          </div>
        </div>
      </div>

      <!-- Input Area -->
      <div class="input-area">
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
            type="primary"
            :disabled="!userInput.trim() || isStreaming"
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
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { NButton, NInput, NIcon, NTag } from 'naive-ui'
import { SendOutline } from '@vicons/ionicons5'
import MarkdownIt from 'markdown-it'

interface Source {
  document_id: string
  filename: string
  chunk_index: number
  page_number: number | null
  content_preview: string
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
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

const quickPrompts = [
  'What is OWASP Top 10?',
  'Explain Zero Trust Architecture',
  'How to prevent SQL injection?',
  'What is incident response?',
]

onMounted(() => {
  loadSessions()
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
}

function switchSession(sessionId: string) {
  currentSessionId.value = sessionId
  messages.value = []
  // TODO: load session messages from API
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
  await scrollToBottom()

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        session_id: currentSessionId.value,
      }),
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
          if (event.type === 'token') {
            streamingContent.value += event.content
            await scrollToBottom()
          } else if (event.type === 'guardrail') {
            streamingContent.value = '⚠️ ' + event.content
            await scrollToBottom()
          } else if (event.type === 'done') {
            sources = event.sources || []
          }
        } catch {
          // skip malformed lines
        }
      }
    }

    // Finalize message
    messages.value.push({
      role: 'assistant',
      content: streamingContent.value,
      sources,
    })

    // Refresh sessions list
    await loadSessions()
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: 'Error: Failed to get response. Please check that the backend is running.',
    })
    console.error('Chat error:', e)
  } finally {
    isStreaming.value = false
    streamingContent.value = ''
    await scrollToBottom()
  }
}

function renderMarkdown(text: string): string {
  return md.render(text)
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
  flex-direction: column;
  gap: 2px;
}

.session-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.session-item.active {
  background: rgba(99, 226, 183, 0.1);
  border: 1px solid rgba(99, 226, 183, 0.2);
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

.sources {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
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

.input-wrapper {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  max-width: 800px;
  margin: 0 auto;
}
</style>
