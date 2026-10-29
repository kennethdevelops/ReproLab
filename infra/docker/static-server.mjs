// Minimal static file server with SPA fallback for the built ReproLab frontend.
import { readFile, stat } from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'

const dist = path.resolve('dist')
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
}

http
  .createServer(async (req, res) => {
    const url = new URL(req.url ?? '/', 'http://localhost')
    let file = path.join(dist, path.normalize(decodeURIComponent(url.pathname)))
    if (!file.startsWith(dist)) file = path.join(dist, 'index.html')
    const info = await stat(file).catch(() => null)
    if (!info || info.isDirectory()) file = path.join(dist, 'index.html')
    const data = await readFile(file)
    res.writeHead(200, {
      'Content-Type': MIME[path.extname(file)] ?? 'application/octet-stream',
      'X-Content-Type-Options': 'nosniff',
    })
    res.end(data)
  })
  .listen(3000, '0.0.0.0')
