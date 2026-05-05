import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
const ROOT = process.cwd(); const files = [];
function walk(dir){ for(const name of readdirSync(dir)){ const path=join(dir,name); const stat=statSync(path); if(stat.isDirectory()) walk(path); else if(/\.(py|md)$/.test(name)) files.push(path); }}
walk(join(ROOT,'tools','entry_trigger_lab')); files.push(join(ROOT,'tools','run_entry_trigger_lab.py'));
const source = files.map((file)=>readFileSync(file,'utf8')).join('\n');
test('entry trigger lab remains read-only and advisory-only',()=>{ assert.match(source,/readOnlyDataPlane/); assert.match(source,/entryTriggerLabOnly/); assert.doesNotMatch(source,/orderSendAllowed["']?\s*[:=]\s*True/); assert.doesNotMatch(source,/brokerExecutionAllowed["']?\s*[:=]\s*True/); assert.doesNotMatch(source,/livePresetMutationAllowed["']?\s*[:=]\s*True/); });
test('entry trigger lab does not contain MT5 execution operations',()=>{ assert.doesNotMatch(source,/\bOrderSend\b|\bOrderSendAsync\b|\bPositionClose\b|\bOrderModify\b|\bCTrade\b|TRADE_ACTION_DEAL/); assert.doesNotMatch(source, /writesMt5OrderRequest["']?\s*[:=]\s*True|writesMt5Preset["']?\s*[:=]\s*True|telegramCommandExecutionAllowed["']?\s*[:=]\s*True/); });
test('telegram text is Chinese-first',()=>{ const text=readFileSync(join(ROOT,'tools','entry_trigger_lab','telegram_text.py'),'utf8'); assert.match(text,/入场触发实验室/); assert.match(text,/不会下单/); assert.match(text,/等待二次确认/); });
