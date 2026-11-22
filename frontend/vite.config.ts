import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'DalaLink — Mobilidade Urbana de Luanda',
        short_name: 'DalaLink',
        description:
          'Plataforma de mobilidade urbana, bilhética QR e transporte corporativo em Luanda, Angola.',
        theme_color: '#0D7C5F',
        background_color: '#F8FAFC',
        display: 'standalone',
        lang: 'pt-AO',
      },
    }),
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  },
});
