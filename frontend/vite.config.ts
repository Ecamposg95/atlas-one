import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { visualizer } from 'rollup-plugin-visualizer'

// `ANALIZAR=1 npm run build` deja dist/stats.html (treemap) y dist/stats.json
// (datos crudos) para auditar qué entra a cada chunk. No se activa en CI.
const analizar = process.env.ANALIZAR === '1'

export default defineConfig({
  plugins: [
    react(),
    ...(analizar
      ? [
          visualizer({ filename: 'dist/stats.html', template: 'treemap', gzipSize: true }),
          visualizer({ filename: 'dist/stats.json', template: 'raw-data' }),
        ]
      : []),
  ],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    minify: 'esbuild',
    rollupOptions: {
      output: {
        // Función y no objeto: con la forma objeto `react/jsx-runtime` (que
        // react-chartjs-2 importa y no estaba listado) caía en `charts`, y
        // TODOS los componentes importaban `jsx` desde ahí: chart.js (184 KB)
        // viajaba con el login. Aquí se casa por ruta, incluidos los envoltorios
        // CJS de commonjs (`\0.../react/jsx-runtime.js?commonjs-...`).
        manualChunks(id: string) {
          if (/[\\/]node_modules[\\/](react|react-dom|react-router-dom|react-router|@remix-run[\\/]router|scheduler)[\\/]/.test(id)) return 'vendor'
          if (/[\\/]node_modules[\\/](chart\.js|react-chartjs-2|@kurkle[\\/]color)[\\/]/.test(id)) return 'charts'
          if (/[\\/]node_modules[\\/](zustand|axios)[\\/]/.test(id)) return 'store'
        },
      },
    },
  },
})
