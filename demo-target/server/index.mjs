// Demo store HTTP server: serves the built storefront and a small JSON API.
// No framework on purpose: fewer dependencies in an intentionally exposed test target.
//
// Usage: node server/index.mjs [--port 4173] [--mode buggy|fixed]
// The fixture mode only selects which pre-built bundle and handler set is served.

import { createHash, timingSafeEqual } from 'node:crypto'
import { existsSync } from 'node:fs'
import { readFile, stat } from 'node:fs/promises'
import http from 'node:http'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { parseArgs } from 'node:util'
import { PRODUCTS, SHIPPING_OPTIONS } from './data.mjs'

const { values: args } = parseArgs({
  options: {
    port: { type: 'string', default: process.env.PORT ?? '4173' },
    mode: { type: 'string', default: process.env.DEMO_FIXTURE_MODE ?? 'buggy' },
  },
})
if (!['buggy', 'fixed'].includes(args.mode)) throw new Error(`invalid mode ${args.mode}`)

const root = path.resolve(import.meta.dirname, '..')
const distDir = path.join(root, 'dist', args.mode)

// Server-side fixture overlay, mirroring the client build: fixed handlers live outside server/.
async function loadModule(name) {
  const fixed = path.join(root, 'fixtures', 'fixed', 'server', name)
  const target = args.mode === 'fixed' && existsSync(fixed) ? fixed : path.join(root, 'server', name)
  return import(pathToFileURL(target).href)
}

const { validateCoupon } = await loadModule('coupons.mjs')
const { createProfileStore } = await loadModule('profile.mjs')

let profileStore = createProfileStore()

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.json': 'application/json',
}

const MAX_BODY = 16 * 1024

function send(res, status, body, headers = {}) {
  const payload = typeof body === 'string' ? body : JSON.stringify(body)
  res.writeHead(status, {
    'Content-Type': typeof body === 'string' ? 'text/plain; charset=utf-8' : 'application/json',
    'Cache-Control': 'no-store',
    ...headers,
  })
  res.end(payload)
}

async function readJson(req) {
  let size = 0
  const chunks = []
  for await (const chunk of req) {
    size += chunk.length
    if (size > MAX_BODY) throw Object.assign(new Error('body too large'), { status: 413 })
    chunks.push(chunk)
  }
  try {
    return chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {}
  } catch {
    throw Object.assign(new Error('invalid JSON'), { status: 400 })
  }
}

function adminAuthorised(req) {
  const expected = process.env.DEMO_ADMIN_TOKEN
  const given = req.headers['x-admin-token']
  if (!expected || typeof given !== 'string') return false
  const a = createHash('sha256').update(expected).digest()
  const b = createHash('sha256').update(given).digest()
  return timingSafeEqual(a, b)
}

async function handleApi(req, res, url) {
  const route = `${req.method} ${url.pathname}`
  switch (route) {
    case 'GET /api/health':
      return send(res, 200, { status: 'ok' })
    case 'GET /api/products':
      return send(res, 200, { products: PRODUCTS })
    case 'GET /api/shipping-options':
      return send(res, 200, { options: SHIPPING_OPTIONS })
    case 'POST /api/coupons/validate': {
      const body = await readJson(req)
      return send(res, 200, validateCoupon(body.code))
    }
    case 'GET /api/profile':
      return send(res, 200, profileStore.get())
    case 'PUT /api/profile': {
      const body = await readJson(req)
      const result = profileStore.update(body)
      return send(res, result.ok ? 200 : 422, result)
    }
    case 'POST /__admin/reset':
      if (!adminAuthorised(req)) return send(res, 403, { error: 'forbidden' })
      profileStore = createProfileStore()
      return send(res, 200, { status: 'reset' })
    default:
      return send(res, 404, { error: 'not found' })
  }
}

async function serveStatic(res, url) {
  const requested = path.normalize(decodeURIComponent(url.pathname)).replace(/^([/\\])+/, '')
  let file = path.join(distDir, requested)
  if (!file.startsWith(distDir)) return send(res, 400, 'bad path')
  const info = await stat(file).catch(() => null)
  // SPA fallback: unknown paths without an extension render the app shell.
  if (!info || info.isDirectory()) file = path.join(distDir, 'index.html')
  const data = await readFile(file).catch(() => null)
  if (!data) return send(res, 404, 'not found')
  res.writeHead(200, {
    'Content-Type': MIME[path.extname(file)] ?? 'application/octet-stream',
    'Cache-Control': file.endsWith('index.html') ? 'no-store' : 'public, max-age=3600',
    'X-Content-Type-Options': 'nosniff',
  })
  res.end(data)
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', 'http://localhost')
  try {
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/__admin/')) {
      await handleApi(req, res, url)
    } else if (req.method === 'GET' || req.method === 'HEAD') {
      await serveStatic(res, url)
    } else {
      send(res, 405, { error: 'method not allowed' })
    }
  } catch (err) {
    send(res, err.status ?? 500, { error: err.status ? err.message : 'internal error' })
  }
})

server.listen(Number(args.port), '0.0.0.0', () => {
  console.log(JSON.stringify({ msg: 'demo store listening', port: Number(args.port) }))
})
