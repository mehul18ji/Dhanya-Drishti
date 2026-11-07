import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Frontend dev server contract (PRD §21): http://localhost:5173
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
})
