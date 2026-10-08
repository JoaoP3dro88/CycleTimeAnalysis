import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'
import fs from 'fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Subpath onde o frontend fica publicado no IIS:
//   https://ct0devtefsrv01.br.bosch.com/CycleTimeAnalysis/
// Troque aqui se o nome da pasta/aplicação no IIS for outro.
const PROD_BASE = '/CycleTimeAnalysis/'

// Vite plugin (apenas DEV): serve MediaPipe WASM de node_modules com MIME correto
function mediapipeWasmPlugin() {
  const wasmDir = path.resolve(
    __dirname,
    'node_modules/@mediapipe/tasks-vision/wasm'
  )
  return {
    name: 'mediapipe-wasm',
    configureServer(server) {
      server.middlewares.use('/mediapipe-wasm', (req, res, next) => {
        const filePath = path.join(wasmDir, req.url)
        if (!fs.existsSync(filePath)) { next(); return }
        if (filePath.endsWith('.wasm')) {
          res.setHeader('Content-Type', 'application/wasm')
        } else if (filePath.endsWith('.js')) {
          res.setHeader('Content-Type', 'application/javascript')
        }
        res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin')
        fs.createReadStream(filePath).pipe(res)
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  base: mode === 'production' ? PROD_BASE : '/',
  plugins: [react(), mediapipeWasmPlugin()],
  build: {
    // Saída padrão: frontend/dist  ->  copiar o CONTEÚDO para o IIS
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
}))