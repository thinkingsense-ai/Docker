import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Dev: `npm run dev` proxies the layer's routes to a running thinking layer (default http://localhost:8097).
const layer = process.env.LAYER_URL ?? 'http://localhost:8097'
const routes = ['/login', '/logout', '/whoami', '/packs', '/ask', '/status', '/starters', '/conversations', '/preferences', '/decisions']

export default defineConfig({
  plugins: [react()],
  server: { proxy: Object.fromEntries(routes.map((r) => [r, layer])) },
  test: { environment: 'node' },
})
