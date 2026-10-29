// Oracle tests: assert the CORRECT behaviour for each defect fixture.
// They are expected to fail on the buggy build (for the intended reason) and pass on the fixed build.
// This directory is private evaluation material and is excluded from repository indexing.
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.oracle\.ts$/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 20_000,
  expect: { timeout: 3_000 },
  reporter: [['list']],
  use: {
    baseURL: process.env.ORACLE_BASE_URL ?? 'http://localhost:4173',
    trace: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
