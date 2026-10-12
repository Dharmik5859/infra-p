import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// In development the API runs separately (uvicorn on :8000); proxy /api to it
// so the app can always use relative URLs. In production the backend serves
// the built app itself, so the same URLs work unchanged.
//
// Keep the target on 127.0.0.1: the dev server and the backend run on the
// same machine (also in GitHub Codespaces). Pointing it at a forwarded
// *.app.github.dev URL sends every API call through the Codespaces tunnel,
// whose sign-in redirect the browser then blocks as a CORS error. Set
// API_URL only for a backend that really runs elsewhere.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': { target: process.env.API_URL || 'http://127.0.0.1:8000', changeOrigin: true } },
  },
});
