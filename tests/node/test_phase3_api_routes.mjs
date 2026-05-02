import assert from 'node:assert/strict'
import test from 'node:test'
import phase3Routes from '../../Dashboard/phase3_api_routes.js'

test('phase3 path detection includes vibe and ai v2', () => {
  assert.equal(phase3Routes.isPhase3Path('/api/vibe-coding/generate'), true)
  assert.equal(phase3Routes.isPhase3Path('/api/ai-analysis-v2/run'), true)
  assert.equal(phase3Routes.isPhase3Path('/api/kline/ai-overlays'), true)
  assert.equal(phase3Routes.isPhase3Path('/api/latest'), false)
})

test('safety envelope forbids live mutation', () => {
  assert.equal(phase3Routes.PHASE3_API_SAFETY.orderSendAllowed, false)
  assert.equal(phase3Routes.PHASE3_API_SAFETY.livePresetMutationAllowed, false)
  assert.equal(phase3Routes.PHASE3_API_SAFETY.canOverrideKillSwitch, false)
})
