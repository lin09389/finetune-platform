import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5173,
    strictPort: true,
    // Frontend uses absolute API_BASE_URL (http://127.0.0.1:8010) directly.
    // Keep dev server free of route-overlapping proxies so SPA paths like
    // /training and /device are always handled by Vite history fallback.
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  optimizeDeps: {
    // Only crawl the application entry. Generated Storybook output may live
    // beside it and must not participate in the development dependency scan.
    entries: ['index.html']
  },
  build: {
    cssCodeSplit: true,
    chunkSizeWarningLimit: 1400,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined

          if (id.includes('antd') || id.includes('@ant-design') || id.includes('/rc-')) return 'vendor-ui'
          if (id.includes('echarts') || id.includes('recharts')) return 'vendor-charts'
          if (id.includes('react-markdown') || id.includes('remark-gfm')) return 'vendor-markdown'
          if (id.includes('zustand')) return 'vendor-store'

          return undefined
        }
      }
    }
  },
})
