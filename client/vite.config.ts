import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/device': 'http://127.0.0.1:8000',
      '/models': 'http://127.0.0.1:8000',
      '/datasets': 'http://127.0.0.1:8000',
      '/training': 'http://127.0.0.1:8000',
      '/inference': 'http://127.0.0.1:8000',
      '/workspace': 'http://127.0.0.1:8000',
      '/model-center': 'http://127.0.0.1:8000',
      '/agent': 'http://127.0.0.1:8000',
      '/context': 'http://127.0.0.1:8000',
      '/cloud': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/api': 'http://127.0.0.1:8000',
      '/v2': 'http://127.0.0.1:8000',
      '/files': 'http://127.0.0.1:8000',
      '/tasks': 'http://127.0.0.1:8000'
    }
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  }
})
