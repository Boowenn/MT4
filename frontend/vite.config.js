import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';

export default defineConfig({
  base: '/vue/',
  plugins: [vue()],
  build: {
    outDir: '../Dashboard/vue-dist',
    emptyOutDir: true
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      '/QuantGod_': 'http://127.0.0.1:8080'
    }
  }
});
