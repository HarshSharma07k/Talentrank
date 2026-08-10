import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    // jsdom, not the default node environment: history.ts touches
    // localStorage/window directly (enhancements/12). Minimal setup scoped to
    // what this doc needs -- the fuller Vitest/component-testing story is 17's.
    environment: 'jsdom',
  },
})
