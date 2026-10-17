import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The build goes straight into app/static/, which app/api.py serves at /, so Posit
// Connect runs one FastAPI app for both the API and the dashboard.
// base './' keeps every asset path relative, so it works under /content/<guid>/ too.
// `npm run dev` proxies /api to the FastAPI app on port 8000 (start it with app/testme.sh).
export default defineConfig({
  plugins: [react()],
  base: './',
  build: { outDir: '../app/static', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  test: { environment: 'node', include: ['src/**/*.test.js'] },
})
