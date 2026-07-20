import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const appVersion = '2.0.0';
const remoteBackend = 'http://10.8.0.105:9120';
const apiProxy = {
  '/__ki_remote_session': {
    target: remoteBackend,
    changeOrigin: true,
    cookieDomainRewrite: '',
    rewrite: () => '/',
  },
  '/api': {
    target: remoteBackend,
    changeOrigin: true,
  },
};

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
          if (id.includes('@xyflow')) return 'xyflow-vendor';
          if (id.includes('react-markdown') || id.includes('remark-gfm')) return 'markdown-vendor';
          if (id.includes('framer-motion')) return 'motion-vendor';
          if (id.includes('lucide-react')) return 'icons-vendor';
          if (id.includes('three')) return 'three-vendor';
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
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
  },
});
