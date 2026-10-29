# Windows equivalent of the Makefile targets.
# Usage: .\scripts\rl.ps1 <target>   e.g. .\scripts\rl.ps1 dev
param([Parameter(Mandatory = $true)][string]$Target)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function In-Dir([string]$dir, [scriptblock]$block) {
    Push-Location (Join-Path $root $dir)
    try { & $block; if ($LASTEXITCODE -ne 0) { throw "failed in $dir (exit $LASTEXITCODE)" } }
    finally { Pop-Location }
}

switch ($Target) {
    { $_ -in 'dev', 'up' } { docker compose up --build -d }
    'down'           { docker compose down }
    'logs'           { docker compose logs -f --tail=100 }
    'migrate'        { docker compose run --rm migrate alembic upgrade head }
    'seed'           { docker compose run --rm migrate python -m reprolab.db.seed }
    'reset-demo'     { docker compose exec api python -m reprolab.demo.reset }
    'test-backend'   { In-Dir 'backend' { uv run pytest } }
    'test-frontend'  { In-Dir 'frontend' { npm test } }
    'test-demo'      { In-Dir 'demo-target' { npm test } }
    'test' {
        In-Dir 'backend' { uv run pytest }
        In-Dir 'frontend' { npm test }
        In-Dir 'demo-target' { npm test }
    }
    'verify-oracles' { In-Dir 'demo-target' { npm run build; npm run verify-oracles -- --runs 2 } }
    'lint' {
        In-Dir 'backend' { uv run ruff check .; uv run ruff format --check . }
        In-Dir 'frontend' { npm run lint }
    }
    'typecheck' {
        In-Dir 'backend' { uv run mypy }
        In-Dir 'frontend' { npm run typecheck }
        In-Dir 'demo-target' { npm run typecheck }
    }
    'clean-artifacts' {
        $answer = Read-Host 'Delete ALL stored investigation artifacts? [y/N]'
        if ($answer -eq 'y') { docker compose run --rm --entrypoint sh api -c 'rm -rf /data/artifacts/*' }
        else { 'aborted' }
    }
    default { throw "unknown target '$Target'" }
}
