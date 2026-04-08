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
  },
  build: {
    cssCodeSplit: true,
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined

          if (id.includes('antd') || id.includes('@ant-design') || id.includes('rc-')) return 'vendor-antd'
          if (id.includes('echarts') || id.includes('recharts')) return 'vendor-charts'
          if (id.includes('react-markdown') || id.includes('remark-gfm')) return 'vendor-markdown'
          if (id.includes('zustand')) return 'vendor-store'

          return undefined
        }
      }
    }
  },
})
