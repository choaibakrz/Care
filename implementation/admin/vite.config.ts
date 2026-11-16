import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// The production build is served by the clinic server at /admin/ (src/admin_web.rs), so its
// assets live under /admin/; the dev server and the e2e tests keep /.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/admin/' : '/',
  plugins: [react()],
}))
