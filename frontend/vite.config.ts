import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import tailwindcss from '@tailwindcss/vite'
import path from "path"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  build: {
    // Optimizaciones de build
    rollupOptions: {
      output: {
        // Code splitting manual para mejorar carga inicial
        manualChunks: {
          // Separar vendor libraries
          'react-vendor': ['react', 'react-dom', 'react-router'],
          // Separar UI components
          'ui-vendor': ['@radix-ui/react-dialog', '@radix-ui/react-dropdown-menu', '@radix-ui/react-select'],
        },
      },
    },
    // Minificar código
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true, // Eliminar console.log en producción
        drop_debugger: true,
      },
    },
    // Chunk size warnings
    chunkSizeWarningLimit: 1000,
    // Optimizar assets
    assetsInlineLimit: 4096, // Inline assets menores a 4KB
  },
  // Optimizar dependencias pre-bundladas
  optimizeDeps: {
    include: ['react', 'react-dom', 'react-router'],
  },
})
