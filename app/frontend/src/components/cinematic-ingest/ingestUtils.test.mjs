import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import ts from 'typescript';

async function importTypescriptModule(sourcePath) {
  const dir = mkdtempSync(join(tmpdir(), 'ki-ingest-utils-'));
  const copySource = readFileSync(new URL('./ingestCopy.ts', import.meta.url), 'utf8');
  const compiledCopy = ts.transpileModule(copySource, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
      verbatimModuleSyntax: true,
    },
  }).outputText;
  writeFileSync(join(dir, 'ingestCopy.mjs'), compiledCopy);

  const source = readFileSync(sourcePath, 'utf8').replace("from './ingestCopy';", "from './ingestCopy.mjs';");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
      verbatimModuleSyntax: true,
    },
  }).outputText;
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

test('processingTrackHint explains running pending and error states', () => {
  assert.equal(
    utils.processingTrackHint({
      id: 'task-running',
      ingest_type: 'douyin_share',
      status: 'running',
      progress_stages: [
        { key: 'fetch', label: '抓取视频', status: 'done' },
        { key: 'asr', label: '转写原文', status: 'active' },
        { key: 'summary', label: 'AI 总结', status: 'pending' },
      ],
    }, 0, 0),
    '正在转写原文 · 局部流程同步推进',
  );
  assert.equal(utils.processingTrackHint(null, 3, 0), '3 个任务排队 · 等待资源调度');
  assert.equal(utils.processingTrackHint(null, 0, 2), '2 个异常任务 · 可重试或删除');
  assert.equal(
    utils.processingTrackHint({
      id: 'task-error',
      ingest_type: 'douyin_share',
      status: 'running',
      progress_stages: [{ key: 'summary', label: 'AI 总结', status: 'error' }],
    }, 0, 0),
    'AI 总结失败 · 等待重试或清理',
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
