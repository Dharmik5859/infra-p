import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// In development the API runs separately (uvicorn on :8000); proxy /api to it
// so the app can always use relative URLs. In production the backend serves
// the built app itself, so the same URLs work unchanged.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': process.env.API_URL || 'https://improved-space-journey-w4rrv6rx5w6cgxxv-8000.app.github.dev' },
  },
});
