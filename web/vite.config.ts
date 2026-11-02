import { defineConfig } from 'vite'

export default defineConfig({
  base: './',
  build: {
    chunkSizeWarningLimit: 1500,
  },
  server: {
    port: 5173,
  },
})
