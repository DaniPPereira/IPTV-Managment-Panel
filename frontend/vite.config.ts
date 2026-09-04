import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 18443,
    proxy: {
      '/api': 'http://127.0.0.1:18000',
      '/m3u': 'http://127.0.0.1:18000',
      '/epg': 'http://127.0.0.1:18000',
      '/health': 'http://127.0.0.1:18000',
      '/get.php': 'http://127.0.0.1:18000',
      '/player_api.php': 'http://127.0.0.1:18000',
      '/stalker_portal': 'http://127.0.0.1:18000',
      '/c': 'http://127.0.0.1:18000',
    },
  },
})
