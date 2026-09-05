import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The Financial Doctor frontend talks to the FastAPI backend either through
// the Vite dev-server proxy (dev) or directly (build served elsewhere).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/demo': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/cases': 'http://localhost:8000',
      '/outcomes': 'http://localhost:8000',
      '/investigations': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
})