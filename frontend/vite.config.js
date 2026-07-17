import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],

  server: {
    // Proxy local: redireciona /api → backend Flask durante o desenvolvimento
    // Assim o frontend em localhost:5173 consegue falar com localhost:8080
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },

  build: {
    // Pasta de saída do build de produção (usada pelo Railway)
    outDir: 'dist',
  },
})
