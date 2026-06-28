import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const appVersion = '1.3.13';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    chunkSizeWarningLimit: 1800,
    rollupOptions: {
      output: {
        entryFileNames: `assets/[name]-${appVersion}-[hash].js`,
        chunkFileNames: `assets/[name]-${appVersion}-[hash].js`,
        assetFileNames: `assets/[name]-${appVersion}-[hash][extname]`,
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('@xyflow') || id.includes('vis-network') || id.includes('vis-data')) return 'graph-vendor';
          if (id.includes('react-markdown') || id.includes('remark-gfm')) return 'markdown-vendor';
          if (id.includes('framer-motion')) return 'motion-vendor';
          if (id.includes('lucide-react')) return 'icons-vendor';
          if (id.includes('react') || id.includes('react-dom') || id.includes('react-router-dom')) return 'react-vendor';
          return 'vendor';
        },
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
