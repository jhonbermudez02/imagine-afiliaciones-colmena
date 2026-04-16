import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 8105,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/docs': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/openapi.json': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
});
