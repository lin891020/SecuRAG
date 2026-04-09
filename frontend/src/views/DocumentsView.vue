<template>
  <div class="documents-container">
    <div class="documents-header">
      <h1>Knowledge Base</h1>
      <p class="subtitle">Upload security documents to build your knowledge base</p>
    </div>

    <!-- Upload Area -->
    <div class="upload-section">
      <n-upload
        :custom-request="handleUpload"
        :show-file-list="false"
        accept=".pdf,.txt,.md"
        :disabled="uploading"
      >
        <n-upload-dragger>
          <div class="upload-content">
            <n-icon size="48" :depth="3">
              <cloud-upload-outline />
            </n-icon>
            <p class="upload-text">
              Drag & drop files here, or click to browse
            </p>
            <p class="upload-hint">Supports PDF, TXT, Markdown</p>
          </div>
        </n-upload-dragger>
      </n-upload>

      <n-progress
        v-if="uploading"
        type="line"
        status="info"
        :percentage="100"
        :processing="true"
        style="margin-top: 12px"
      />
    </div>

    <!-- Documents Table -->
    <div class="documents-list">
      <n-data-table
        :columns="columns"
        :data="documents"
        :loading="loading"
        :bordered="false"
        :row-key="(row: DocRow) => row.id"
        size="small"
      />

      <div v-if="!loading && documents.length === 0" class="empty-docs">
        <n-icon size="64" :depth="5">
          <document-text-outline />
        </n-icon>
        <p>No documents uploaded yet</p>
        <p class="hint">Upload security policies, guidelines, or documentation to get started</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, h, onMounted } from 'vue'
import {
  NUpload,
  NUploadDragger,
  NIcon,
  NDataTable,
  NButton,
  NTag,
  NProgress,
  useMessage,
} from 'naive-ui'
import type { DataTableColumns, UploadCustomRequestOptions } from 'naive-ui'
import {
  CloudUploadOutline,
  DocumentTextOutline,
  TrashOutline,
} from '@vicons/ionicons5'

interface DocRow {
  id: string
  filename: string
  file_type: string
  file_size: number
  chunk_count: number
  status: string
  created_at: string
}

const message = useMessage()
const documents = ref<DocRow[]>([])
const loading = ref(false)
const uploading = ref(false)

const columns: DataTableColumns<DocRow> = [
  {
    title: 'Filename',
    key: 'filename',
    ellipsis: { tooltip: true },
  },
  {
    title: 'Type',
    key: 'file_type',
    width: 80,
    render(row) {
      return h(NTag, { size: 'small', bordered: false }, { default: () => row.file_type.toUpperCase() })
    },
  },
  {
    title: 'Size',
    key: 'file_size',
    width: 100,
    render(row) {
      return formatSize(row.file_size)
    },
  },
  {
    title: 'Chunks',
    key: 'chunk_count',
    width: 80,
  },
  {
    title: 'Status',
    key: 'status',
    width: 100,
    render(row) {
      const typeMap: Record<string, 'success' | 'warning' | 'error'> = {
        ready: 'success',
        processing: 'warning',
        error: 'error',
      }
      return h(
        NTag,
        { size: 'small', type: typeMap[row.status] || 'default', bordered: false },
        { default: () => row.status }
      )
    },
  },
  {
    title: 'Uploaded',
    key: 'created_at',
    width: 120,
    render(row) {
      return new Date(row.created_at).toLocaleDateString()
    },
  },
  {
    title: '',
    key: 'actions',
    width: 60,
    render(row) {
      return h(
        NButton,
        {
          size: 'small',
          quaternary: true,
          type: 'error',
          onClick: () => deleteDocument(row.id),
        },
        { icon: () => h(NIcon, null, { default: () => h(TrashOutline) }) }
      )
    },
  },
]

onMounted(() => {
  loadDocuments()
})

async function loadDocuments() {
  loading.value = true
  try {
    const resp = await fetch('/api/documents')
    if (resp.ok) {
      const data = await resp.json()
      documents.value = data.documents
    }
  } catch (e) {
    message.error('Failed to load documents')
  } finally {
    loading.value = false
  }
}

async function handleUpload({ file }: UploadCustomRequestOptions) {
  if (!file.file) return
  uploading.value = true

  const formData = new FormData()
  formData.append('file', file.file)

  try {
    const resp = await fetch('/api/documents/upload', {
      method: 'POST',
      body: formData,
    })

    if (!resp.ok) {
      const err = await resp.json()
      throw new Error(err.detail || 'Upload failed')
    }

    message.success(`"${file.name}" uploaded and indexed successfully`)
    await loadDocuments()
  } catch (e: any) {
    message.error(e.message || 'Upload failed')
  } finally {
    uploading.value = false
  }
}

async function deleteDocument(id: string) {
  try {
    const resp = await fetch(`/api/documents/${id}`, { method: 'DELETE' })
    if (resp.ok) {
      message.success('Document deleted')
      await loadDocuments()
    } else {
      message.error('Failed to delete document')
    }
  } catch {
    message.error('Failed to delete document')
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.documents-container {
  max-width: 900px;
  margin: 0 auto;
  padding: 32px 24px;
  color: #e0e0e0;
}

.documents-header {
  margin-bottom: 24px;
}

.documents-header h1 {
  font-size: 24px;
  color: #63e2b7;
  margin: 0 0 4px;
}

.subtitle {
  color: #888;
  font-size: 14px;
}

.upload-section {
  margin-bottom: 32px;
}

.upload-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
}

.upload-text {
  font-size: 14px;
  color: #ccc;
}

.upload-hint {
  font-size: 12px;
  color: #888;
}

.documents-list {
  min-height: 200px;
}

.empty-docs {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 48px;
  color: #666;
}

.empty-docs .hint {
  font-size: 13px;
  color: #555;
}
</style>
