// Runs every oracle test against freshly started buggy and fixed servers and checks that:
//   - on the fixed build each oracle passes;
//   - on the buggy build each oracle fails, and the failure happens inside an "oracle:" step
//     (an intended assertion), not during "setup:" (selector/navigation problems).
// Usage: node scripts/verify-oracles.mjs [--runs 2] [--grep D01]
// Writes a JSON summary to stdout's last line and exits non-zero on any mismatch.

import { spawn } from 'node:child_process'
import { mkdtemp, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { parseArgs } from 'node:util'

const { values: args } = parseArgs({
  options: {
    runs: { type: 'string', default: '1' },
    grep: { type: 'string' },
    'buggy-port': { type: 'string', default: '4183' },
    'fixed-port': { type: 'string', default: '4184' },
  },
})

const root = path.resolve(import.meta.dirname, '..')
const children = []

function startServer(mode, port) {
  const child = spawn(process.execPath, ['server/index.mjs', '--mode', mode, '--port', port], {
    cwd: root,
    stdio: 'ignore',
    env: { ...process.env, DEMO_ADMIN_TOKEN: 'oracle-verifier' },
  })
  children.push(child)
  return child
}

async function waitHealthy(port) {
  const deadline = Date.now() + 10_000
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/api/health`)
      if (r.ok) return
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 150))
  }
  throw new Error(`server on ${port} did not become healthy`)
}

async function runOracles(baseUrl) {
  const dir = await mkdtemp(path.join(tmpdir(), 'oracles-'))
  const outFile = path.join(dir, 'report.json')
  const cliArgs = ['playwright', 'test', '-c', 'fixtures/oracles/playwright.config.ts', '--reporter=json']
  if (args.grep) cliArgs.push('--grep', args.grep)
  await new Promise((resolve, reject) => {
    const child = spawn('npx', cliArgs, {
      cwd: root,
      shell: process.platform === 'win32',
      stdio: ['ignore', 'ignore', 'inherit'],
      env: { ...process.env, ORACLE_BASE_URL: baseUrl, PLAYWRIGHT_JSON_OUTPUT_NAME: outFile },
    })
    child.on('exit', () => resolve())
    child.on('error', reject)
  })
  return JSON.parse(await readFile(outFile, 'utf8'))
}

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

function summarise(report) {
  const out = []
  for (const suite of report.suites) {
    for (const spec of walkSpecs(suite)) {
      const result = spec.tests[0].results.at(-1)
      out.push({
        title: spec.title,
        status: result.status,
        failedStep: result.status === 'passed' ? null : failingStep(result.steps),
        error: result.error?.message?.split('\n')[0] ?? null,
      })
    }
  }
  return out
}

let mismatches = 0
const summary = []
try {
  startServer('buggy', args['buggy-port'])
  startServer('fixed', args['fixed-port'])
  await Promise.all([waitHealthy(args['buggy-port']), waitHealthy(args['fixed-port'])])

  for (let run = 1; run <= Number(args.runs); run++) {
    for (const [mode, port] of [['buggy', args['buggy-port']], ['fixed', args['fixed-port']]]) {
      const results = summarise(await runOracles(`http://127.0.0.1:${port}`))
      for (const r of results) {
        const ok =
          mode === 'fixed'
            ? r.status === 'passed'
            : r.status === 'failed' && typeof r.failedStep === 'string' && r.failedStep.startsWith('oracle:')
        if (!ok) mismatches++
        summary.push({ run, mode, ...r, verdict: ok ? 'as_expected' : 'MISMATCH' })
        console.error(`[run ${run}] ${mode.padEnd(5)} ${ok ? 'OK      ' : 'MISMATCH'} ${r.title} -> ${r.status}${r.failedStep ? ` @ ${r.failedStep}` : ''}`)
      }
    }
  }
} finally {
  for (const child of children) child.kill()
}

console.log(JSON.stringify({ mismatches, results: summary }))
process.exit(mismatches === 0 && summary.length > 0 ? 0 : 1)
