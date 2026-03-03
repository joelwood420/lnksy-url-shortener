import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/shorten': 'http://localhost:5001',
      '/register': 'http://localhost:5001',
      '/login': 'http://localhost:5001',
      '/logout': 'http://localhost:5001',
      '/my-urls': 'http://localhost:5001',
      '/qr': 'http://localhost:5001',
      '/delete': 'http://localhost:5001',
    },
  },
})
