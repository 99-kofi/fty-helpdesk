import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
      '/webhooks': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true },
    },
    allowedHosts: ['.ngrok-free.app'],
  },
  preview: { port: 4173 },
});
