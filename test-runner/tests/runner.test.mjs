// Spec validation and generation (unit) plus a real buggy/fixed validation of the D01 spec.

import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import path from 'node:path'
import { after, before, test } from 'node:test'

import { generateTest } from '../src/generate.mjs'
import { createRunnerServer } from '../src/server.mjs'
import { validateSpec } from '../src/spec.mjs'

const role = (value, name) => ({ kind: 'role', value, name, exact: false })

export const D01_SPEC = {
  version: 1,
  title: 'Applied coupon persists after reload',
  start_path: '/shop',
  steps: [
    { action: 'click', locator: role('button', 'Add Cast Iron Skillet to cart') },
    { action: 'goto', path: '/checkout' },
    { action: 'fill', locator: { kind: 'label', value: 'Coupon code', name: null, exact: false }, value: 'SAVE10' },
    { action: 'click', locator: role('button', 'Apply coupon') },
    { action: 'wait_for_text', locator: role('complementary', 'Order summary'), value: 'Discount (SAVE10)' },
    { action: 'reload' },
  ],
  assertions: [{ type: 'text_visible', locator: role('complementary', 'Order summary'), value: 'Discount (SAVE10)' }],
}

test('accepts the D01 spec', () => {
  assert.deepEqual(validateSpec(D01_SPEC), [])
})

test('rejects anything outside the allowlist', () => {
  const bad = (patch) => validateSpec({ ...structuredClone(D01_SPEC), ...patch })
  assert.ok(bad({ code: 'process.exit()' }).some((e) => e.includes('unknown field code')))
  assert.ok(bad({ start_path: 'https://evil.example/' }).length)
  assert.ok(bad({ start_path: '//evil.example/' }).length)
  assert.ok(bad({ steps: [{ action: 'evaluate', value: 'alert(1)' }] }).some((e) => e.includes('not allowed')))
  assert.ok(bad({ steps: [{ action: 'click', locator: { kind: 'css', value: 'body' } }] }).length)
  assert.ok(bad({ steps: [{ action: 'goto', path: '/x', value: 'y' }] }).some((e) => e.includes('not allowed for goto')))
  assert.ok(bad({ assertions: [] }).length)
  assert.ok(bad({ assertions: [{ type: 'screenshot_matches', value: 'x' }] }).length)
  assert.ok(validateSpec(null).length)
})

test('generation is deterministic and spec text stays inside string literals', () => {
  const tricky = structuredClone(D01_SPEC)
  tricky.title = "x'); require('child_process').exec('calc'); ('"
  tricky.steps[2].value = '`${process.env.SECRET}`\n})'
  assert.deepEqual(validateSpec(tricky), [])
  const code = generateTest(tricky)
  assert.equal(code, generateTest(structuredClone(tricky)))
  assert.ok(code.includes(JSON.stringify(tricky.title)))
  assert.ok(code.includes(JSON.stringify(tricky.steps[2].value)))
  // Outside string literals the code only contains generator-owned tokens.
  const outside = code.replace(/"(?:[^"\\]|\\.)*"/g, '""')
  assert.ok(!outside.includes('child_process') && !outside.includes('process.env'))
  assert.match(generateTest(D01_SPEC), /assert 1: complementary \\"Order summary\\" shows/)
})

// --- real validation against the demo fixtures ---
const demoRoot = path.resolve(import.meta.dirname, '..', '..', 'demo-target')
const children = []
let runner
let runnerUrl

async function waitHealthy(url) {
  const deadline = Date.now() + 15_000
  while (Date.now() < deadline) {
    try {
      if ((await fetch(url)).ok) return
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 150))
  }
  throw new Error(`${url} not healthy`)
}

before(async () => {
  for (const [mode, port] of [['buggy', '4193'], ['fixed', '4194']]) {
    children.push(spawn(process.execPath, ['server/index.mjs', '--mode', mode, '--port', port], {
      cwd: demoRoot, stdio: 'ignore', env: { ...process.env, DEMO_ADMIN_TOKEN: 'runner-test' },
    }))
    await waitHealthy(`http://127.0.0.1:${port}/api/health`)
  }
  runner = createRunnerServer({ buggyUrl: 'http://127.0.0.1:4193', fixedUrl: 'http://127.0.0.1:4194', adminToken: 'runner-test' })
  await new Promise((r) => runner.listen(0, '127.0.0.1', r))
  runnerUrl = `http://127.0.0.1:${runner.address().port}`
})

after(() => {
  runner?.close()
  for (const c of children) c.kill()
})

const post = (route, body) => fetch(runnerUrl + route, {
  method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
})

test('D01 spec fails on buggy at the assertion and passes on fixed', { timeout: 180_000 }, async () => {
  const r = await post('/validate', { spec: D01_SPEC })
  assert.equal(r.status, 200)
  const body = await r.json()
  assert.equal(body.buggy.outcome, 'assertion_failed', JSON.stringify(body.buggy))
  assert.match(body.buggy.failing_step, /^assert 1/)
  assert.equal(body.fixed.outcome, 'passed', JSON.stringify(body.fixed))
  assert.equal(body.verdict.status, 'validated')
})

test('a broken selector is classified as a setup failure, not a detected bug', { timeout: 180_000 }, async () => {
  const spec = structuredClone(D01_SPEC)
  spec.steps[0].locator.name = 'Add Nonexistent Product to cart'
  const body = await (await post('/validate', { spec })).json()
  assert.equal(body.buggy.outcome, 'setup_failed')
  assert.equal(body.verdict.status, 'invalid')
})

test('invalid specs are refused before anything runs', async () => {
  const r = await post('/validate', { spec: { ...D01_SPEC, steps: [{ action: 'evaluate' }] } })
  assert.equal(r.status, 422)
  assert.equal((await fetch(runnerUrl + '/validate', { method: 'POST', body: 'x' })).status, 415)
})
