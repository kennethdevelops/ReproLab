import react from '@vitejs/plugin-react'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { defineConfig, type Plugin } from 'vite'

const root = import.meta.dirname
const srcDir = path.join(root, 'src')
const fixedDir = path.join(root, 'fixtures', 'fixed', 'src')

/**
 * Fixture overlay: in `fixed` mode, any module under src/ that has a counterpart under
 * fixtures/fixed/src/ is replaced by it. The buggy source in src/ is what gets indexed;
 * the fixes live outside the indexed tree so the agent never sees them.
 */
function fixtureOverlay(mode: string): Plugin {
  return {
    name: 'fixture-overlay',
    enforce: 'pre',
    async resolveId(source, importer, options) {
      if (mode !== 'fixed' || !importer) return null
      const resolved = await this.resolve(source, importer, { ...options, skipSelf: true })
      if (!resolved) return null
      const resolvedPath = path.resolve(resolved.id.split('?')[0])
      if (!resolvedPath.startsWith(srcDir + path.sep)) return null
      const candidate = path.join(fixedDir, path.relative(srcDir, resolvedPath))
      return existsSync(candidate) ? candidate : null
    },
  }
}

export default defineConfig(({ mode }) => ({
  plugins: [fixtureOverlay(mode), react()],
  server: { port: 4173 },
  build: { sourcemap: false },
}))
