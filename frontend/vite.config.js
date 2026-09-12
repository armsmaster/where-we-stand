import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    // В разработке фронтенд поднимается отдельно, API остаётся на бэкенде.
    // В продакшене оба отдаются одним контейнером и прокси не нужен.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // Имена без хешей: сервис отдаётся из одного контейнера, кеш браузера
    // сбрасывается перезапуском, а стабильные имена проще отлаживать.
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name].[ext]',
      },
    },
  },
});
