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

test('buildEventListPath encodes the active topic and search without stale parameters', () => {
  const path = utils.buildEventListPath('格局', '人工 智能', 20);
  const url = new URL(path, 'http://localhost');

  assert.equal(url.pathname, '/api/events');
  assert.equal(url.searchParams.get('topic'), '格局');
  assert.equal(url.searchParams.get('search'), '人工 智能');
  assert.equal(url.searchParams.get('offset'), '20');
  assert.equal(url.searchParams.get('limit'), String(utils.EVENT_BATCH_SIZE));
  assert.equal(utils.buildEventListPath('全部', '', 0).includes('topic='), false);
});

test('mergeEventPages appends later pages without duplicating existing events', () => {
  const firstPage = [{ id: 'event-1' }, { id: 'event-2' }];
  const secondPage = [{ id: 'event-2' }, { id: 'event-3' }];

  assert.deepEqual(utils.mergeEventPages(firstPage, secondPage, true), [
    { id: 'event-1' },
    { id: 'event-2' },
    { id: 'event-3' },
  ]);
  assert.deepEqual(utils.mergeEventPages(firstPage, secondPage, false), secondPage);
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

test('queueProgressStages returns running stages without mutating their status', () => {
  const progress_stages = [
    { key: 'fetch', label: '抓取视频', status: 'done' },
    { key: 'asr', label: '转写原文', status: 'active' },
    { key: 'summary', label: 'AI 总结', status: 'pending' },
    { key: 'store', label: '写入事件', status: 'error' },
  ];
  const item = {
    id: 'task-running',
    ingest_type: 'douyin_share',
    status: 'running',
    progress_stages,
  };

  const result = utils.queueProgressStages(item);

  assert.deepEqual(result, progress_stages);
  assert.notEqual(result, progress_stages);
  result.forEach((stage, index) => assert.notEqual(stage, progress_stages[index]));
  assert.deepEqual(progress_stages, [
    { key: 'fetch', label: '抓取视频', status: 'done' },
    { key: 'asr', label: '转写原文', status: 'active' },
    { key: 'summary', label: 'AI 总结', status: 'pending' },
    { key: 'store', label: '写入事件', status: 'error' },
  ]);
});

test('queueProgressStages maps the first active error-task stage to error without mutation', () => {
  const progress_stages = [
    { key: 'fetch', label: '抓取视频', status: 'done' },
    { key: 'asr', label: '转写原文', status: 'active' },
    { key: 'summary', label: 'AI 总结', status: 'active' },
    { key: 'store', label: '写入事件', status: 'pending' },
  ];
  const item = {
    id: 'task-error-active',
    ingest_type: 'douyin_share',
    status: 'error',
    progress_stages,
  };

  const result = utils.queueProgressStages(item);

  assert.notEqual(result, progress_stages);
  assert.deepEqual(result, [
    { key: 'fetch', label: '抓取视频', status: 'done' },
    { key: 'asr', label: '转写原文', status: 'error' },
    { key: 'summary', label: 'AI 总结', status: 'active' },
    { key: 'store', label: '写入事件', status: 'pending' },
  ]);
  assert.equal(progress_stages[1].status, 'active');
  assert.equal(progress_stages[2].status, 'active');
});

test('queueProgressStages preserves explicit errors and hides compact or missing stages', () => {
  const explicitError = {
    id: 'task-explicit-error',
    ingest_type: 'douyin_share',
    status: 'error',
    progress_stages: [
      { key: 'fetch', label: '抓取视频', status: 'done' },
      { key: 'asr', label: '转写原文', status: 'error' },
    ],
  };

  assert.deepEqual(utils.queueProgressStages(explicitError), explicitError.progress_stages);
  assert.notEqual(utils.queueProgressStages(explicitError), explicitError.progress_stages);
  const noActiveError = {
    id: 'task-error-inactive',
    ingest_type: 'douyin_share',
    status: 'error',
    progress_stages: [
      { key: 'fetch', label: '抓取视频', status: 'done' },
      { key: 'summary', label: 'AI 总结', status: 'pending' },
    ],
  };
  const noActiveResult = utils.queueProgressStages(noActiveError);

  assert.deepEqual(noActiveResult, noActiveError.progress_stages);
  assert.notEqual(noActiveResult, noActiveError.progress_stages);
  noActiveResult.forEach((stage, index) => assert.notEqual(stage, noActiveError.progress_stages[index]));
  assert.deepEqual(utils.queueProgressStages({ id: 'task-pending', ingest_type: 'douyin_share', status: 'pending' }), []);
  assert.deepEqual(utils.queueProgressStages({ id: 'task-done', ingest_type: 'douyin_share', status: 'done' }), []);
  assert.deepEqual(utils.queueProgressStages({ id: 'task-running-missing', ingest_type: 'douyin_share', status: 'running' }), []);
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
  assert.equal(
    utils.processingTrackHint(null, 0, 2, {
      id: 'task-timeout',
      ingest_type: 'douyin_share',
      status: 'error',
      error: 'request timeout',
    }),
    '2 个异常任务 · 请求超时 · 建议重试',
  );
  assert.equal(
    utils.processingTrackHint({
      id: 'task-error',
      ingest_type: 'douyin_share',
      status: 'running',
      error: '401 unauthorized',
      progress_stages: [{ key: 'summary', label: 'AI 总结', status: 'error' }],
    }, 0, 0),
    'AI 总结失败 · 鉴权异常 · 检查配置',
  );
});

test('queueErrorHint maps backend failures to short operator hints', () => {
  assert.equal(utils.queueErrorHint('429 rate limit'), '额度或限流 · 稍后重试');
  assert.equal(utils.queueErrorHint('JSON parse failed'), '解析失败 · 检查来源');
  assert.equal(utils.queueErrorHint('ASR audio decode failed'), '转写失败 · 检查媒体');
  assert.equal(utils.queueErrorHint('unknown failure'), '处理失败 · 查看任务详情');
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
