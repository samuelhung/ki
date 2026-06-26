import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const appVersion = '1.3.3';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        entryFileNames: `assets/[name]-${appVersion}-[hash].js`,
        chunkFileNames: `assets/[name]-${appVersion}-[hash].js`,
        assetFileNames: `assets/[name]-${appVersion}-[hash][extname]`,
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:9120',
    },
  },
});
