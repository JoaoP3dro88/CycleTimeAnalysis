import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'
import fs from 'fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Vite plugin: serve MediaPipe WASM files from node_modules with correct MIME type
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
export default defineConfig({
  plugins: [react(), mediapipeWasmPlugin()],
  server: {
    headers: {
      'Cross-Origin-Opener-Policy': 'same-origin',
      'Cross-Origin-Embedder-Policy': 'require-corp',
    },
  },
})
