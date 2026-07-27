import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';
import {
  assertForwardedCallbacks,
  assertNamedImports,
  assertRequestCoordinatorBehavior,
  combinedSource,
  loadRequestCoordinatorFactory,
  objectArrayValues,
  readSourceModules,
} from '../detailPageContractTestUtils.mjs';

const pageUrl = new URL('../../pages/Ingest.tsx', import.meta.url);
const hookUrl = new URL('./useIngestEvents.ts', import.meta.url);
const workspaceUrl = new URL('./IngestWorkspaceContent.tsx', import.meta.url);
const modules = readSourceModules([pageUrl, hookUrl, workspaceUrl]);
const implementation = combinedSource(modules);
const pageModule = modules.find((module) => module.name === 'Ingest.tsx');
assert.ok(pageModule);
const page = pageModule.source;

test('ingest detail tabs can move while preserving exact definitions and order', () => {
  assert.deepEqual(objectArrayValues(modules, 'DETAIL_TABS'), [
    { key: 'body', label: '转写原文', meta: 'TRANSCRIPT', icon: 'FileText' },
    { key: 'summary', label: 'AI 总结', meta: 'SUMMARY', icon: 'Sparkles' },
    { key: 'questions', label: '关联问题', meta: 'LINKED Q', icon: 'Link2' },
    { key: 'chain', label: '产业分析', meta: 'INDUSTRY', icon: 'Radio' },
  ]);
  assert.match(implementation, /DETAIL_TABS\.map\(\(tab\) =>/);
  assert.match(implementation, /ingest-tab-trigger launcher-action pixel-command/);
});

test('ingest endpoints preserve list mutation upload and status polling contracts', () => {
  assert.match(implementation, /const PAGE_SIZE = 15/);
  assert.match(implementation, /const API_BASE = '\/api\/events'/);
  assert.match(implementation, /sourceId = 'douyin,user-upload,user-concept'/);
  assert.match(implementation, /limit=\$\{PAGE_SIZE\}&offset=0&count=1/);
  assert.match(implementation, /apiFetch\(`\/api\/ingest\/status\/\$\{eventId\}`, \{ signal \}\)/);
  assert.match(implementation, /apiFetch\('\/api\/ingest\/douyin', \{\s*method: 'POST'/);
  assert.match(implementation, /apiFetch\('\/api\/ingest\/file', \{ method: 'POST', timeoutMs: 900_000, body \}\)/);
  assert.match(implementation, /apiFetch\(`\$\{API_BASE\}\/\$\{eventId\}`, \{ method: 'DELETE' \}\)/);
  assert.match(implementation, /void loadEventsRef\.current\(\)/);
});

test('ingest lifecycle source preserves cancellation stale suppression refreshes and errors', () => {
  assert.match(implementation, /eventRequestAbortRef\.current\?\.abort\(\)/);
  assert.match(implementation, /signal: requestController\.signal/);
  assert.match(implementation, /isLatestRequest\(requestSequence, eventRequestSequenceRef\.current\)/);
  assert.match(implementation, /error\?\.name !== 'AbortError'/);
  assert.match(implementation, /statusRequestLifecycleRef\.current\.isCurrent\(sequence\)/);
  assert.match(implementation, /statusRequestLifecycleRef\.current\.abort\(\)/);
  assert.match(implementation, /await loadEvents\(\)/);
  assert.match(implementation, /setEventsError\(error\.message \|\| '加载事件列表失败'\)/);
});

test('ingest labels css hooks and embedded composition can move together', () => {
  for (const label of ['搜索内容标题', '提交抖音视频', '上传文件', '分享文本（从抖音复制）', '分类（可选）']) {
    assert.match(implementation, new RegExp(label));
  }
  assert.match(implementation, /legacy-ingest-root is-shell-embedded cinematic-ingest/);
  assert.match(implementation, /<EmbeddedIngestList/);
  assert.match(implementation, /<ContentDetailPanel/);
  assert.match(implementation, /<EmbeddedIngestWorkspace/);
});

test('request coordinator loader transpiles typed hook exports without resolving React imports', () => {
  const source = `
    import React, { useState } from 'react';
    interface Options { onCommit: (value: string) => void; }
    export function createRequestCoordinator(options: Options) {
      return (value: string) => options.onCommit(value);
    }
  `;
  const module = {
    name: 'typedHook.ts',
    source,
    sourceFile: ts.createSourceFile('typedHook.ts', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS),
  };
  let committed = '';
  const coordinator = loadRequestCoordinatorFactory(module)({ onCommit: (value) => { committed = value; } });
  coordinator('loaded');
  assert.equal(committed, 'loaded');
});

test('ingest extraction forwards callbacks and exports its real request coordinator', async () => {
  assert.ok(existsSync(hookUrl), 'Task 5.6 must add useIngestEvents.ts');
  const hook = readFileSync(hookUrl, 'utf8');
  const hookModule = modules.find((module) => module.name === 'useIngestEvents.ts');
  assert.ok(hookModule);
  assertNamedImports(hookModule, '../ingest/requestLifecycle', ['RequestLifecycle', 'abortableDelay']);
  assertNamedImports(hookModule, '../ingest/ingestRequestPolicy', ['isLatestRequest']);
  await assertRequestCoordinatorBehavior(loadRequestCoordinatorFactory(hookModule));

  assert.ok(existsSync(workspaceUrl), 'Task 5.6 must add IngestWorkspaceContent.tsx');
  assert.match(page, /useIngestEvents\(/);
  assertForwardedCallbacks(pageModule, 'IngestWorkspaceContent', {
    onRetry: 'loadEvents',
    onSelect: 'openDetail',
    onDelete: 'handleDelete',
    onTopicChange: 'handleEmbeddedTopicChange',
    onSearchChange: 'handleEmbeddedSearchChange',
    onSummarize: 'handleEmbeddedSummarize',
    onContemplate: 'details.handleContemplate',
    onLinkQuestions: 'details.handleContemplateLink',
    onChainAnalyze: 'details.handleChainAnalyze',
    onSyncHints: 'details.handleSyncHints',
  });
  assert.doesNotMatch(page, /new RequestLifecycle\(\)|new AbortController\(\)/);
  assert.match(hook, /isLatestRequest|isCurrent|sequence/);
});
