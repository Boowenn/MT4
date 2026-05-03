import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'

const ROOT = process.cwd()

function read(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), 'utf8')
}

test('backend Dockerfile.local keeps the dashboard local and dry-run guarded', () => {
  const dockerfile = read('Dockerfile.local')
  assert.match(dockerfile, /QG_DASHBOARD_HOST=0\.0\.0\.0/)
  assert.match(dockerfile, /QG_DRY_RUN=1/)
  assert.match(dockerfile, /QG_KILL_SWITCH_LOCKED=1/)
  assert.match(dockerfile, /QG_ORDER_SEND_ALLOWED=0/)
  assert.match(dockerfile, /QG_LIVE_PRESET_MUTATION_ALLOWED=0/)
  assert.match(dockerfile, /QG_CREDENTIAL_STORAGE_ALLOWED=0/)
  assert.match(dockerfile, /QG_TELEGRAM_COMMANDS_ALLOWED=0/)
  assert.match(dockerfile, /\/api\/state\/status/)
  assert.doesNotMatch(dockerfile, /TELEGRAM_BOT_TOKEN\s*=/i)
  assert.doesNotMatch(dockerfile, /OPENROUTER_API_KEY\s*=/i)
  assert.doesNotMatch(dockerfile, /PASSWORD\s*=/i)
})

test('backend local Docker entrypoint initializes only the SQLite state file', () => {
  const entrypoint = read('docker/local-entrypoint.sh')
  assert.match(entrypoint, /tools\/run_state_store\.py --db "\$QG_STATE_DB" init/)
  assert.doesNotMatch(entrypoint, /order|broker|webhook|telegram.*command/i)
})
