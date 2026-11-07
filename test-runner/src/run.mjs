// Runs a generated test against one fixture origin and classifies the result.

import { spawn } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const require = createRequire(import.meta.url)
const cli = path.join(path.dirname(require.resolve('@playwright/test/package.json')), 'cli.js')
const TIMEOUT_MS = 90_000
// eslint-disable-next-line no-control-regex
const ANSI = /\u001b\[[0-9;]*m/g
const clean = (text) => text.replace(ANSI, '').slice(0, 2000)

function* walkSpecs(suite) {
  for (const spec of suite.specs ?? []) yield spec
  for (const child of suite.suites ?? []) yield* walkSpecs(child)
}

function failingStep(steps = []) {
  for (const step of steps) {
    if (step.error) return failingStep(step.steps) ?? step.title
  }
  return null
}

export function classify(report) {
  const specs = (report.suites ?? []).flatMap((s) => [...walkSpecs(s)])
  const result = specs[0]?.tests?.[0]?.results?.at(-1)
  if (!result) {
    const message = (report.errors ?? []).map((e) => e.message).join('\n') || 'no test result'
    return { outcome: 'error', failing_step: null, message: clean(message) }
  }
  if (result.status === 'passed') return { outcome: 'passed', failing_step: null, message: '' }
  const step = failingStep(result.steps)
  let message = (result.errors ?? []).map((e) => e.message ?? '').join('\n')
  message = clean(message)
  if (step?.startsWith('assert')) return { outcome: 'assertion_failed', failing_step: step, message }
  if (step?.startsWith('setup')) return { outcome: 'setup_failed', failing_step: step, message }
  return { outcome: 'error', failing_step: step, message }
}

async function reset(baseUrl, token) {
  const r = await fetch(new URL('/__admin/reset', baseUrl), {
    method: 'POST',
    headers: { 'x-admin-token': token ?? '' },
  })
  if (!r.ok) throw new Error(`fixture reset failed: HTTP ${r.status}`)
}

/** Run `code` against `baseUrl` with a fresh browser context after resetting the fixture. */
export async function runAgainst(code, baseUrl, { adminToken } = {}) {
  const started = new Date().toISOString()
  const dir = path.join(root, '.work', randomUUID())
  await mkdir(dir, { recursive: true })
  try {
    await reset(baseUrl, adminToken)
    await writeFile(path.join(dir, 'regression.spec.ts'), code, 'utf8')
    await writeFile(
      path.join(dir, 'playwright.config.mjs'),
      `export default ${JSON.stringify({
        testDir: '.',
        timeout: 30_000,
        retries: 0,
        workers: 1,
        use: { baseURL: baseUrl, trace: 'off', actionTimeout: 5_000, navigationTimeout: 10_000 },
        expect: { timeout: 3_000 },
      })}\n`,
    )
    const out = path.join(dir, 'report.json')
    const log = await new Promise((resolve, reject) => {
      let stderr = ''
      const child = spawn(process.execPath, [cli, 'test', '-c', 'playwright.config.mjs', '--reporter=json'], {
        cwd: dir,
        stdio: ['ignore', 'ignore', 'pipe'],
        env: { PATH: process.env.PATH, SYSTEMROOT: process.env.SYSTEMROOT, PLAYWRIGHT_BROWSERS_PATH:
          process.env.PLAYWRIGHT_BROWSERS_PATH, LOCALAPPDATA: process.env.LOCALAPPDATA, HOME: process.env.HOME,
          USERPROFILE: process.env.USERPROFILE, PLAYWRIGHT_JSON_OUTPUT_NAME: out },
      })
      const timer = setTimeout(() => child.kill('SIGKILL'), TIMEOUT_MS)
      child.stderr.on('data', (d) => {
        stderr += d
      })
      child.on('exit', () => {
        clearTimeout(timer)
        resolve(stderr.slice(-4000))
      })
      child.on('error', reject)
    })
    let report
    try {
      report = JSON.parse(await readFile(out, 'utf8'))
    } catch {
      return { started, finished: new Date().toISOString(), outcome: 'error', failing_step: null,
        message: 'runner produced no report', log }
    }
    return { started, finished: new Date().toISOString(), ...classify(report), log }
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
}

/** Validated = fails on buggy for the intended reason (an assert step) and passes on fixed. */
export function verdict(buggy, fixed) {
  if (buggy.outcome === 'assertion_failed' && fixed.outcome === 'passed') {
    return { status: 'validated', reason: 'Fails on the buggy fixture at an assertion and passes on the fixed fixture.' }
  }
  if (buggy.outcome === 'setup_failed' || fixed.outcome === 'setup_failed') {
    return { status: 'invalid', reason: 'A setup step failed (selector or navigation problem), not the intended assertion.' }
  }
  if (buggy.outcome === 'passed') {
    return { status: 'invalid', reason: 'The test passes on the buggy fixture, so it does not detect the bug.' }
  }
  if (fixed.outcome !== 'passed') {
    return { status: 'invalid', reason: 'The test fails on the fixed fixture.' }
  }
  return { status: 'error', reason: 'The runner could not complete both executions.' }
}

export async function readJson(file) {
  return JSON.parse(await readFile(file, 'utf8'))
}
