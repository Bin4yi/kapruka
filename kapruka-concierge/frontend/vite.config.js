import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/stream': { target:'http://localhost:8001', changeOrigin:true },
      '/action': { target:'http://localhost:8001', changeOrigin:true },
      '/api':    { target:'http://localhost:8001', changeOrigin:true },
    },
  },
})
