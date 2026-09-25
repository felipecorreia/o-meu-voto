import {defineConfig, loadEnv} from 'vite';
import react from '@vitejs/plugin-react';

// Same-origin API: in dev the local service is proxied under /api/v1, the same path Cloudflare
// Pages routes to the API in production (ADR 0005), so the page never needs CORS or an absolute
// API URL. The proxy target comes from BR_ELECTIONS_API_ORIGIN (environment or web-next/.env)
// and defaults to the local run of docs/local-run.md.
const DEFAULT_API_ORIGIN = 'http://127.0.0.1:8000';

export default defineConfig(({mode}) => {
  const env = {...loadEnv(mode, process.cwd(), 'BR_ELECTIONS_'), ...process.env};
  const apiOrigin = env.BR_ELECTIONS_API_ORIGIN || DEFAULT_API_ORIGIN;
  return {
    plugins: [react()],
    server: {
      port: 5199,
      strictPort: true,
      // Lets a review board embed the dev server from a sandboxed (opaque-origin) iframe; Vite's
      // default CORS allow-list rejects `Origin: null` for module scripts. Dev-server only.
      cors: true,
      proxy: {
        '/api/v1': {target: apiOrigin, changeOrigin: false},
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
    },
  };
});
