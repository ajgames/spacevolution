import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { shipAssets } from './scripts/sync-ship.ts'

// https://vite.dev/config/
export default defineConfig({
  plugins: [shipAssets(), tailwindcss(), react()],
  // Vite crawls every .html under the root for dependencies by default, which
  // would pull in blender/export/preview.html and its CDN import map.
  optimizeDeps: { entries: ['index.html'] },
  // Lets the dev server answer through an ngrok tunnel. The leading dot allows
  // any subdomain, so a new tunnel address doesn't need a config change.
  server: { allowedHosts: ['.ngrok-free.dev'] },
})
