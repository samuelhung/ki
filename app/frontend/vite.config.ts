import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv, type ProxyOptions } from 'vite';

const appVersion = '2.0.0';
const remoteBackend = 'http://10.8.0.105:9120';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'KI_');
  const remoteApiToken = env.KI_REMOTE_API_TOKEN?.trim();
  const protectedProxy: ProxyOptions = {
    target: remoteBackend,
    changeOrigin: true,
    configure(proxy) {
      proxy.on('proxyReq', (proxyReq) => {
        if (remoteApiToken) {
          proxyReq.setHeader('Authorization', `Bearer ${remoteApiToken}`);
        }
      });
    },
  };
  const apiProxy = {
    '/api': protectedProxy,
    '/ingest': protectedProxy,
    '/releases': protectedProxy,
  };

  return {
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
  };
});
