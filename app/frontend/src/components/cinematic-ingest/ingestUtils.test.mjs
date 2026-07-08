import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

async function importTypescriptModule(sourcePath) {
  const source = readFileSync(sourcePath, 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
      verbatimModuleSyntax: true,
    },
  }).outputText;
  const dir = mkdtempSync(join(tmpdir(), 'ki-ingest-utils-'));
  const modulePath = join(dir, 'ingestUtils.mjs');
  writeFileSync(modulePath, compiled);
  return import(modulePath);
}

const utils = await importTypescriptModule(new URL('./ingestUtils.ts', import.meta.url));

test('compactIndexTitle limits titles to 18 visible characters', () => {
  assert.equal(utils.compactIndexTitle('一二三四五六七八九十十一十二十三十四十五十六十七十八十九'), '一二三四五六七八九十十一十二十三十四...');
  assert.equal(utils.compactIndexTitle('短标题'), '短标题');
});

test('visibleProgressStages returns previous current and next two stages', () => {
  const stages = [
    { key: 'a', label: 'A', status: 'done' },
    { key: 'b', label: 'B', status: 'active' },
    { key: 'c', label: 'C', status: 'pending' },
    { key: 'd', label: 'D', status: 'pending' },
    { key: 'e', label: 'E', status: 'pending' },
  ];

  assert.deepEqual(
    utils.visibleProgressStages(stages).map((stage) => [stage.key, stage.isCurrent]),
    [['a', false], ['b', true], ['c', false], ['d', false]],
  );
});

test('applyDeletedQueueCounts subtracts tombstoned tasks that are still returned by polling', () => {
  const counts = utils.normalizeQueueStatusCounts({ pending: 2, running: 1, error: 3 });
  const deletedTasks = new Map([
    ['task-error', { deletedAt: Date.now(), status: 'error' }],
    ['task-missing', { deletedAt: Date.now(), status: 'pending' }],
  ]);
  const rawItems = [
    { id: 'task-error', ingest_type: 'douyin_share', status: 'error' },
    { id: 'task-live', ingest_type: 'douyin_share', status: 'pending' },
  ];

  assert.deepEqual(utils.applyDeletedQueueCounts(counts, rawItems, deletedTasks), {
    pending: 2,
    running: 1,
    done: 0,
    error: 2,
  });
});
