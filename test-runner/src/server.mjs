// HTTP front of the isolated test runner.
//   POST /generate  {spec}  -> {code}                  (validate + generate only)
//   POST /validate  {spec}  -> {code, buggy, fixed, verdict}
// Targets come from the environment (BUGGY_URL, FIXED_URL), never from the request, so the runner
// can only execute tests against the controlled demo fixtures. Only JSON specs are accepted; there
// is no way to submit source code.

import http from 'node:http'
import { parseArgs } from 'node:util'

import { generateTest } from './generate.mjs'
import { runAgainst, verdict } from './run.mjs'
import { validateSpec } from './spec.mjs'

const MAX_BODY = 64 * 1024

export function createRunnerServer({ buggyUrl, fixedUrl, adminToken }) {
  let busy = false

  async function readBody(req) {
    let size = 0
    const chunks = []
    for await (const chunk of req) {
      size += chunk.length
      if (size > MAX_BODY) throw Object.assign(new Error('body too large'), { status: 413 })
      chunks.push(chunk)
    }
    try {
      return JSON.parse(Buffer.concat(chunks).toString('utf8'))
    } catch {
      throw Object.assign(new Error('invalid JSON'), { status: 400 })
    }
  }

  function send(res, status, body) {
    res.writeHead(status, { 'content-type': 'application/json' })
    res.end(JSON.stringify(body))
  }

  return http.createServer(async (req, res) => {
    try {
      if (req.method === 'GET' && req.url === '/healthz') return send(res, 200, { status: 'ok' })
      if (req.method !== 'POST' || !['/generate', '/validate'].includes(req.url)) {
        return send(res, 404, { error: 'not found' })
      }
      if (!(req.headers['content-type'] ?? '').startsWith('application/json')) {
        return send(res, 415, { error: 'application/json required' })
      }
      const body = await readBody(req)
      const errors = validateSpec(body?.spec)
      if (errors.length) return send(res, 422, { error: 'invalid spec', details: errors })
      const code = generateTest(body.spec)
      if (req.url === '/generate') return send(res, 200, { code })
      if (busy) return send(res, 429, { error: 'runner busy' })
      busy = true
      try {
        const buggy = await runAgainst(code, buggyUrl, { adminToken })
        const fixed = await runAgainst(code, fixedUrl, { adminToken })
        return send(res, 200, { code, buggy, fixed, verdict: verdict(buggy, fixed) })
      } finally {
        busy = false
      }
    } catch (err) {
      return send(res, err.status ?? 500, { error: err.status ? err.message : 'internal error' })
    }
  })
}

if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith('server.mjs')) {
  const { values } = parseArgs({ options: { port: { type: 'string', default: process.env.PORT ?? '4300' } } })
  const buggyUrl = process.env.BUGGY_URL
  const fixedUrl = process.env.FIXED_URL
  if (!buggyUrl || !fixedUrl) {
    console.error('BUGGY_URL and FIXED_URL are required')
    process.exit(2)
  }
  createRunnerServer({ buggyUrl, fixedUrl, adminToken: process.env.DEMO_ADMIN_TOKEN })
    .listen(Number(values.port), process.env.HOST ?? '127.0.0.1', () => {
      console.log(`test-runner listening on ${values.port}`)
    })
}
