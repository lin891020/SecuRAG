import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 8311,
    // Vite 6 預設擋掉不認識的 Host header。透過 Caddy 走 securag.test 進來時
    // Host 就不是 localhost，沒有這行會回 "Blocked request"。
    allowedHosts: ['securag.test'],
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})
