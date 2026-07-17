import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';
export default defineConfig({
  plugins: [sveltekit()],
  server: { proxy: { '/api': { target: process.env.API_PROXY ?? 'http://localhost:8000', changeOrigin: true, rewrite: p => p.replace(/^\/api/, '') } } }
});
